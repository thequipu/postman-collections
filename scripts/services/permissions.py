"""FLOW-Permissions-Full: Complete RBAC testing with 2 users, 3 entity types.

Deps: DataSource → Schema → Realm + 2 Keycloak users (USER role).
Tests: VIEW, EDIT, ADMIN permissions on DATA_FABRIC, SCHEMA, DATA_SOURCE entities.
Keycloak admin creds from S3: kc_admin_user, kc_admin_password.
"""

from flowlib.core import req, build_setup, build_collection, write_flow
from flowlib.setup import realm_delete_prereq


def generate():
    base = "app_base_url"

    # Keycloak admin token prerequest (used for user create/delete steps)
    kc_admin_pre = [
        "// Get Keycloak admin token for user management",
        "const kcUrl = pm.environment.get('keycloak_url') || pm.environment.get('kc_url');",
        "const kcRealm = 'master';",
        "const kcUser = pm.environment.get('kc_admin_user') || 'admin';",
        "const kcPass = pm.environment.get('kc_admin_password') || 'admin123';",
        "const tokenUrl = kcUrl.replace(/\\/realms\\/.*/, '') + '/realms/' + kcRealm + '/protocol/openid-connect/token';",
        "pm.sendRequest({",
        "  url: tokenUrl,",
        "  method: 'POST',",
        "  header: {'Content-Type': 'application/x-www-form-urlencoded'},",
        "  body: {mode:'urlencoded', urlencoded:[",
        "    {key:'grant_type',value:'password'},",
        "    {key:'client_id',value:'admin-cli'},",
        "    {key:'username',value:kcUser},",
        "    {key:'password',value:kcPass}",
        "  ]}",
        "}, (err, res) => {",
        "  if(err||!res) { console.log('KC admin token error:', err); return; }",
        "  const t = res.json();",
        "  pm.collectionVariables.set('_kc_admin_token', t.access_token);",
        "  console.log('KC admin token acquired');",
        "});",
    ]

    items = [
        build_setup(base, "/actuator/health",
                    clear_vars=["dsId", "schemaName", "schemaId", "realmId",
                                "user1Id", "user2Id", "user1Name", "user2Name",
                                "viewPermId", "editPermId", "adminPermId",
                                "viewerRoleId", "adminRoleId",
                                "upId1", "upId2", "upId3", "upId4", "upId5",
                                "rpId1", "rpId2", "rpId3"]),

        # ═══ PHASE 0: Create Test Entities (DataSource → Schema → Realm) ═══

        req("01a Create DataSource (dep)", "POST", "/datasource",
            ["const code = pm.response.code;",
             "pm.test('01a Create DS 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01a Create DS');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.dataSourceModel||b.data||b;",
             "if(d.id||d.sourceId) pm.collectionVariables.set('dsId', String(d.id||d.sourceId));"],
            base=base,
            body={"name": "pm_flow_perm_ds_{{$timestamp}}",
                  "driverType": "{{driverType}}", "dbHostName": "{{dbHost}}",
                  "dbPort": "{{dbPort}}", "databaseName": "{{dbName}}",
                  "dbUserName": "{{dbUser}}", "dbPassword": "{{dbPassword}}",
                  "aesRandomIV": "{{aesRandomIV}}", "dbSchema": "{{dbSchema}}",
                  "driverClassName": "{{driverClassName}}", "deleted": False}),

        req("01b Create Schema (dep)", "POST", "/schema",
            ["const code = pm.response.code;",
             "pm.test('01b Create schema 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01b Create Schema');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.schemaModel||b.data||b;",
             "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
             "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));"],
            base=base,
            body={"schemaName": "pm_flow_perm_schema_{{$timestamp}}",
                  "description": "Permissions flow dep"}),

        req("01c Create Realm (dep)", "POST", "/realm",
            ["const code = pm.response.code;",
             "pm.test('01c Create realm 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01c Create Realm');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const d=b.realmModel||b.data||b;",
             "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));"],
            base=base,
            body={"name": "pm_flow_perm_realm_{{$timestamp}}",
                  "description": "Permissions flow dep"}),

        # ═══ PHASE 1: Create 2 Test Users via Keycloak Admin API ═══

        req("02a Create User1 (viewer)", "POST", "/admin/realms/{{tenant_id}}/users",
            ["pm.test('02a Create user1 201', () => pm.expect(pm.response.code).to.be.oneOf([201,409]));",
             "// Extract user ID from Location header",
             "const loc = pm.response.headers.get('Location') || '';",
             "const uid = loc.split('/').pop();",
             "if(uid && pm.response.code===201) pm.collectionVariables.set('user1Id', uid);",
             "console.log('User1 created: '+uid);"],
            base="keycloak_admin_url",
            body={"username": "pmflow-viewer-{{$timestamp}}", "enabled": True,
                  "credentials": [{"type": "password", "value": "Test@123", "temporary": False}]},
            prerequest=kc_admin_pre,
            extra_headers=[{"key": "Authorization", "value": "Bearer {{_kc_admin_token}}"}]),

        req("02b Set User1 Name var", "GET", "/permissions",
            ["pm.test('02b ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base,
            prerequest=[
                "// Store the generated username for later lookups",
                "const ts = pm.collectionVariables.get('user1Id') ? '' : '';",
                "pm.collectionVariables.set('user1Name', 'pmflow-viewer-' + pm.variables.replaceIn('{{$timestamp}}'));",
            ]),

        req("03a Create User2 (admin)", "POST", "/admin/realms/{{tenant_id}}/users",
            ["pm.test('03a Create user2 201', () => pm.expect(pm.response.code).to.be.oneOf([201,409]));",
             "const loc = pm.response.headers.get('Location') || '';",
             "const uid = loc.split('/').pop();",
             "if(uid && pm.response.code===201) pm.collectionVariables.set('user2Id', uid);",
             "console.log('User2 created: '+uid);"],
            base="keycloak_admin_url",
            body={"username": "pmflow-admin-{{$timestamp}}", "enabled": True,
                  "credentials": [{"type": "password", "value": "Test@123", "temporary": False}]},
            prerequest=kc_admin_pre,
            extra_headers=[{"key": "Authorization", "value": "Bearer {{_kc_admin_token}}"}]),

        req("04 Get All Users", "GET", "/user-permission/get-all-users",
            ["pm.test('04 Get all users 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('04 has users data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        # ═══ PHASE 2: Create Permissions ═══

        req("05 Get Existing Permissions", "GET", "/permissions",
            ["pm.test('05 Permissions 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('05 is array', () => pm.expect(Array.isArray(b)).to.be.true);"],
            base=base),

        req("06 Create Permissions", "POST", "/permissions",
            ["pm.test('06 Create perms 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:(b.data||[]);",
             "// Capture permission IDs by name",
             "for(const p of arr){",
             "  if(p.name==='VIEW') pm.collectionVariables.set('viewPermId', String(p.id));",
             "  if(p.name==='EDIT') pm.collectionVariables.set('editPermId', String(p.id));",
             "  if(p.name==='ADMIN') pm.collectionVariables.set('adminPermId', String(p.id));",
             "}",
             "pm.test('06 captured VIEW id', () => pm.expect(pm.collectionVariables.get('viewPermId')).to.not.eql(''));",
             "console.log('Perms: VIEW='+pm.collectionVariables.get('viewPermId')+', EDIT='+pm.collectionVariables.get('editPermId')+', ADMIN='+pm.collectionVariables.get('adminPermId'));"],
            base=base,
            body=[{"name": "VIEW", "description": "Read only access"},
                  {"name": "EDIT", "description": "Read write access"},
                  {"name": "ADMIN", "description": "Full administrative access"},
                  {"name": "ROW_ACCESS", "description": "Row level data access"}]),

        req("07 Verify Permissions", "GET", "/permissions",
            ["pm.test('07 Permissions 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const names=b.map(p=>p.name);",
             "pm.test('07 has VIEW', () => pm.expect(names).to.include('VIEW'));",
             "pm.test('07 has EDIT', () => pm.expect(names).to.include('EDIT'));",
             "pm.test('07 has ADMIN', () => pm.expect(names).to.include('ADMIN'));"],
            base=base),

        # ═══ PHASE 3: Create Roles ═══

        req("08 Get Existing Roles", "GET", "/roles",
            ["pm.test('08 Roles 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("09 Create Viewer Role", "POST", "/roles",
            ["pm.test('09 Create viewer role 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('viewerRoleId', String(arr[0].id));",
             "console.log('Viewer role id='+pm.collectionVariables.get('viewerRoleId'));"],
            base=base,
            body=[{"name": "pm_flow_viewer", "description": "View only role"}]),

        req("10 Create Admin Role", "POST", "/roles",
            ["pm.test('10 Create admin role 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('adminRoleId', String(arr[0].id));"],
            base=base,
            body=[{"name": "pm_flow_admin", "description": "Admin role"}]),

        req("11 Verify Roles", "GET", "/roles",
            ["pm.test('11 Roles 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const names=(Array.isArray(b)?b:[]).map(r=>r.name);",
             "pm.test('11 has viewer role', () => pm.expect(names).to.include('pm_flow_viewer'));",
             "pm.test('11 has admin role', () => pm.expect(names).to.include('pm_flow_admin'));"],
            base=base),

        # ═══ PHASE 4: Assign User-Permissions on REAL entities ═══

        req("12 User1 VIEW on Fabric", "POST", "/user-permission",
            ["pm.test('12 Assign 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('upId1', String(arr[0].id));"],
            base=base,
            body=[{"userIdentifier": "{{user1Name}}", "entityType": "DATA_FABRIC",
                   "entityId": "{{realmId}}", "permission": {"id": "{{viewPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("13 User1 VIEW on DataSource", "POST", "/user-permission",
            ["pm.test('13 Assign 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('upId2', String(arr[0].id));"],
            base=base,
            body=[{"userIdentifier": "{{user1Name}}", "entityType": "DATA_SOURCE",
                   "entityId": "{{dsId}}", "permission": {"id": "{{viewPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("14 User2 EDIT on Fabric", "POST", "/user-permission",
            ["pm.test('14 Assign 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('upId3', String(arr[0].id));"],
            base=base,
            body=[{"userIdentifier": "{{user2Name}}", "entityType": "DATA_FABRIC",
                   "entityId": "{{realmId}}", "permission": {"id": "{{editPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("15 User2 ADMIN on Schema", "POST", "/user-permission",
            ["pm.test('15 Assign 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('upId4', String(arr[0].id));"],
            base=base,
            body=[{"userIdentifier": "{{user2Name}}", "entityType": "SCHEMA",
                   "entityId": "{{schemaId}}", "permission": {"id": "{{adminPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("16 User2 EDIT on DataSource", "POST", "/user-permission",
            ["pm.test('16 Assign 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('upId5', String(arr[0].id));"],
            base=base,
            body=[{"userIdentifier": "{{user2Name}}", "entityType": "DATA_SOURCE",
                   "entityId": "{{dsId}}", "permission": {"id": "{{editPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        # ═══ PHASE 5: VERIFY User1 (viewer) — VIEW only ═══

        req("17 User1 Perms by UserID", "GET", "/user-permission/permission_by_userid?userId={{user1Name}}&page=0&size=20",
            ["pm.test('17 Get user1 perms 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const content=b.content||b.data||[];",
             "const permNames=content.map(p=>p.permission?p.permission.name:p.permissionName||'');",
             "pm.test('17 user1 has VIEW', () => pm.expect(permNames).to.include('VIEW'));",
             "pm.test('17 user1 no EDIT', () => pm.expect(permNames).to.not.include('EDIT'));",
             "pm.test('17 user1 no ADMIN', () => pm.expect(permNames).to.not.include('ADMIN'));"],
            base=base),

        req("18 User1 VIEW on Fabric exists", "GET", "/user-permission/exists?entityType=DATA_FABRIC&userIdentifier={{user1Name}}&permissionNames=VIEW",
            ["pm.test('18 Exists 200', () => pm.response.to.have.status(200));",
             "let b=false; try{b=pm.response.json();}catch(e){}",
             "pm.test('18 user1 VIEW on fabric = true', () => pm.expect(b).to.eql(true));"],
            base=base),

        req("19 User1 EDIT on Fabric NOT exists", "GET", "/user-permission/exists?entityType=DATA_FABRIC&userIdentifier={{user1Name}}&permissionNames=EDIT",
            ["pm.test('19 Exists 200', () => pm.response.to.have.status(200));",
             "let b=true; try{b=pm.response.json();}catch(e){}",
             "pm.test('19 user1 EDIT on fabric = false', () => pm.expect(b).to.eql(false));"],
            base=base),

        req("20 User1 VIEW on DS exists", "GET", "/user-permission/exists?entityType=DATA_SOURCE&userIdentifier={{user1Name}}&permissionNames=VIEW",
            ["pm.test('20 Exists 200', () => pm.response.to.have.status(200));",
             "let b=false; try{b=pm.response.json();}catch(e){}",
             "pm.test('20 user1 VIEW on DS = true', () => pm.expect(b).to.eql(true));"],
            base=base),

        req("21 User1 Perms on Fabric", "GET", "/user-permission/permission_by_userid_and_entity_type?userId={{user1Name}}&entityType=DATA_FABRIC&page=0&size=20",
            ["pm.test('21 Perms 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const content=b.content||b.data||[];",
             "pm.test('21 only VIEW on fabric', () => {",
             "  const permNames=content.map(p=>p.permission?p.permission.name:'');",
             "  pm.expect(permNames).to.include('VIEW');",
             "  pm.expect(permNames).to.not.include('ADMIN');",
             "});"],
            base=base),

        # ═══ PHASE 6: VERIFY User2 (admin) — EDIT+ADMIN ═══

        req("22 User2 Perms by UserID", "GET", "/user-permission/permission_by_userid?userId={{user2Name}}&page=0&size=20",
            ["pm.test('22 Get user2 perms 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const content=b.content||b.data||[];",
             "const permNames=content.map(p=>p.permission?p.permission.name:'');",
             "pm.test('22 user2 has EDIT', () => pm.expect(permNames).to.include('EDIT'));",
             "pm.test('22 user2 has ADMIN', () => pm.expect(permNames).to.include('ADMIN'));"],
            base=base),

        req("23 User2 EDIT on Fabric exists", "GET", "/user-permission/exists?entityType=DATA_FABRIC&userIdentifier={{user2Name}}&permissionNames=EDIT",
            ["pm.test('23 user2 EDIT = true', () => { pm.response.to.have.status(200); let b=pm.response.json(); pm.expect(b).to.eql(true); });"],
            base=base),

        req("24 User2 ADMIN on Schema exists", "GET", "/user-permission/exists?entityType=SCHEMA&userIdentifier={{user2Name}}&permissionNames=ADMIN",
            ["pm.test('24 user2 ADMIN on schema = true', () => { pm.response.to.have.status(200); let b=pm.response.json(); pm.expect(b).to.eql(true); });"],
            base=base),

        req("25 User2 EDIT on DS exists", "GET", "/user-permission/exists?entityType=DATA_SOURCE&userIdentifier={{user2Name}}&permissionNames=EDIT",
            ["pm.test('25 user2 EDIT on DS = true', () => { pm.response.to.have.status(200); let b=pm.response.json(); pm.expect(b).to.eql(true); });"],
            base=base),

        req("26 User2 Perms on Schema", "GET", "/user-permission/permission_by_userid_and_entity_type?userId={{user2Name}}&entityType=SCHEMA&page=0&size=20",
            ["pm.test('26 Perms 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const content=b.content||b.data||[];",
             "pm.test('26 user2 ADMIN on schema', () => {",
             "  const names=content.map(p=>p.permission?p.permission.name:'');",
             "  pm.expect(names).to.include('ADMIN');",
             "});"],
            base=base),

        # ═══ PHASE 7: Verify general query endpoints ═══

        req("27 All User-Permissions", "GET", "/user-permission?page=0&size=100",
            ["pm.test('27 All user-perms 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('27 has paginated content', () => pm.expect(b.content||b.data).to.not.be.undefined);"],
            base=base),

        req("28 Current User Permissions", "GET", "/user-permission/user",
            ["pm.test('28 Current user perms 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("29 Entity360 Paths", "GET", "/user-permission/entity360-paths",
            ["pm.test('29 E360 paths 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("30 User-Perm by Entity", "GET", "/user-permission/permission?entityType=DATA_FABRIC&entityId={{realmId}}",
            ["pm.test('30 Perm by entity 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("31 User-Perm by Entity Type", "GET", "/user-permission/permission_by_entity?entityType=DATA_FABRIC&page=0&size=20",
            ["pm.test('31 Perm by entity type 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("32 All User IDs", "GET", "/user-permission/user_ids",
            ["pm.test('32 User IDs 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('32 is array', () => pm.expect(Array.isArray(b)).to.be.true);"],
            base=base),

        # ═══ PHASE 8: Roles — assign to roles, verify ═══

        req("33 Role-Perm: viewer→VIEW on Fabric", "POST", "/role-permission",
            ["pm.test('33 Create role-perm 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('rpId1', String(arr[0].id));"],
            base=base,
            body=[{"role": {"id": "{{viewerRoleId}}"}, "entityType": "DATA_FABRIC",
                   "entityId": "{{realmId}}", "permission": {"id": "{{viewPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("34 Role-Perm: admin→EDIT+ADMIN on Fabric", "POST", "/role-permission",
            ["pm.test('34 Create role-perms 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "const arr=Array.isArray(b)?b:[b];",
             "if(arr[0]&&arr[0].id) pm.collectionVariables.set('rpId2', String(arr[0].id));",
             "if(arr[1]&&arr[1].id) pm.collectionVariables.set('rpId3', String(arr[1].id));"],
            base=base,
            body=[{"role": {"id": "{{adminRoleId}}"}, "entityType": "DATA_FABRIC",
                   "entityId": "{{realmId}}", "permission": {"id": "{{editPermId}}"},
                   "grantedBy": "pmflow-test"},
                  {"role": {"id": "{{adminRoleId}}"}, "entityType": "DATA_FABRIC",
                   "entityId": "{{realmId}}", "permission": {"id": "{{adminPermId}}"},
                   "grantedBy": "pmflow-test"}]),

        req("35 Get Role-Permissions", "GET", "/role-permission?page=0&size=100",
            ["pm.test('35 Role-perms 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("36 Viewer has VIEW", "GET", "/role-permission/exists?entityType=DATA_FABRIC&role=pm_flow_viewer&permissionNames=VIEW",
            ["pm.test('36 viewer VIEW = true', () => { pm.response.to.have.status(200); let b=pm.response.json(); pm.expect(b).to.eql(true); });"],
            base=base),

        req("37 Viewer NOT ADMIN", "GET", "/role-permission/exists?entityType=DATA_FABRIC&role=pm_flow_viewer&permissionNames=ADMIN",
            ["pm.test('37 viewer ADMIN = false', () => { pm.response.to.have.status(200); let b=pm.response.json(); pm.expect(b).to.eql(false); });"],
            base=base),

        req("38 Role-Perm by User", "GET", "/role-permission/user",
            ["pm.test('38 Role-perm user 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("39 Role-Perm by Entity", "GET", "/role-permission/permission?entityType=DATA_FABRIC&entityId={{realmId}}",
            ["pm.test('39 Role-perm entity 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("40 Role-Perm by Entity Type", "GET", "/role-permission/permission_by_entity?entityType=DATA_FABRIC&page=0&size=20",
            ["pm.test('40 Role-perm entity type 200', () => pm.response.to.have.status(200));"],
            base=base),

        # ═══ PHASE 9: Update & Deactivate ═══

        req("41 Deactivate User1", "POST", "/user-permission/updateUser?username={{user1Name}}&status=false",
            ["pm.test('41 Deactivate user1 200', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        # ═══ PHASE 10: Cleanup ═══

        req("42 Delete User-Permissions", "DELETE", "/user-permission/delete?ids={{upId1}},{{upId2}},{{upId3}},{{upId4}},{{upId5}}",
            ["pm.test('42 Delete user-perms 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("43 Delete Role-Permissions", "DELETE", "/role-permission/delete?ids={{rpId1}},{{rpId2}},{{rpId3}}",
            ["pm.test('43 Delete role-perms 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("44 Delete Roles", "DELETE", "/roles/delete?ids={{viewerRoleId}},{{adminRoleId}}",
            ["pm.test('44 Delete roles 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("45 Delete User1 from Keycloak", "DELETE", "/admin/realms/{{tenant_id}}/users/{{user1Id}}",
            ["pm.test('45 Delete user1 204', () => pm.expect(pm.response.code).to.be.oneOf([204,404]));"],
            base="keycloak_admin_url",
            prerequest=kc_admin_pre,
            extra_headers=[{"key": "Authorization", "value": "Bearer {{_kc_admin_token}}"}]),

        req("46 Delete User2 from Keycloak", "DELETE", "/admin/realms/{{tenant_id}}/users/{{user2Id}}",
            ["pm.test('46 Delete user2 204', () => pm.expect(pm.response.code).to.be.oneOf([204,404]));"],
            base="keycloak_admin_url",
            prerequest=kc_admin_pre,
            extra_headers=[{"key": "Authorization", "value": "Bearer {{_kc_admin_token}}"}]),

        req("47 Delete Realm", "DELETE", "/realm/{{realmId}}",
            ["pm.test('47 Delete realm 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base, prerequest=realm_delete_prereq()),

        req("48 Delete Schema", "DELETE", "/schema?schemaName={{schemaName}}",
            ["pm.test('48 Delete schema 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        req("49 Delete DataSource", "DELETE", "/datasource/{{dsId}}",
            ["pm.test('49 Delete DS 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base),

        # Teardown
        req("99 Teardown", "DELETE", "/realm/{{realmId}}",
            ["pm.test('99 teardown tolerant', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, prerequest=realm_delete_prereq()),
    ]

    col = build_collection(
        name="FLOW - Permissions Full",
        description="Complete RBAC testing: 2 Keycloak users (USER role) + permissions + roles on real entities.\n\n"
                    "User1 (viewer): VIEW on DATA_FABRIC + DATA_SOURCE\n"
                    "User2 (admin): EDIT on DATA_FABRIC + ADMIN on SCHEMA + EDIT on DATA_SOURCE\n\n"
                    "Verifies: exists=true/false per user per entity, permission_by_userid, role-permission exists.\n\n"
                    "Requires: DB config + kc_admin_user + kc_admin_password + keycloak_admin_url in environment.",
        folder_name="Permissions Full",
        items=items,
        extra_variables=[
            {"key": "dsId",          "value": "", "type": "string"},
            {"key": "schemaName",    "value": "", "type": "string"},
            {"key": "schemaId",      "value": "", "type": "string"},
            {"key": "realmId",       "value": "", "type": "string"},
            {"key": "user1Id",       "value": "", "type": "string"},
            {"key": "user2Id",       "value": "", "type": "string"},
            {"key": "user1Name",     "value": "", "type": "string"},
            {"key": "user2Name",     "value": "", "type": "string"},
            {"key": "viewPermId",    "value": "", "type": "string"},
            {"key": "editPermId",    "value": "", "type": "string"},
            {"key": "adminPermId",   "value": "", "type": "string"},
            {"key": "viewerRoleId",  "value": "", "type": "string"},
            {"key": "adminRoleId",   "value": "", "type": "string"},
            {"key": "upId1",         "value": "", "type": "string"},
            {"key": "upId2",         "value": "", "type": "string"},
            {"key": "upId3",         "value": "", "type": "string"},
            {"key": "upId4",         "value": "", "type": "string"},
            {"key": "upId5",         "value": "", "type": "string"},
            {"key": "rpId1",         "value": "", "type": "string"},
            {"key": "rpId2",         "value": "", "type": "string"},
            {"key": "rpId3",         "value": "", "type": "string"},
            {"key": "_kc_admin_token", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Permissions-CRUD.postman_collection.json", col)
