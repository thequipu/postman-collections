"""Reusable setup steps for creating DS → Schema → Version → Graph → Realm.

Every flow that needs a schema uses this to ensure entities from the datasource
are properly added to the schema graph.
"""

from .core import req


def create_ds_step(step, base="app_base_url"):
    """Create datasource and capture ID + catalog name."""
    return req(f"{step} Create DataSource", "POST", "/datasource",
        [f"const code=pm.response.code;",
         f"pm.test('{step} DS 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.dataSourceModel||b.data||b;",
         "if(d.id||d.sourceId) pm.collectionVariables.set('dsId', String(d.id||d.sourceId));",
         "if(d.dataCatalogName) pm.collectionVariables.set('dataCatalogName', d.dataCatalogName);",
         f"console.log('DS id='+(d.id||d.sourceId));"],
        base=base,
        body={"name": "pm-flow-ds-{{$timestamp}}",
              "driverType": "{{driverType}}", "dbHostName": "{{dbHost}}",
              "dbPort": "{{dbPort}}", "databaseName": "{{dbName}}",
              "dbUserName": "{{dbUser}}", "dbPassword": "{{dbPassword}}",
              "aesRandomIV": "{{aesRandomIV}}", "dbSchema": "{{dbSchema}}",
              "driverClassName": "{{driverClassName}}", "deleted": False})


def fetch_metadata_step(step):
    """Fetch table metadata from transformation service → build entity list."""
    return req(f"{step} Fetch Metadata", "POST", "/test-connection/metadata",
        [f"pm.test('{step} Metadata reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400]));",
         "let tables = [];",
         "if(pm.response.code===200){",
         "  let b={}; try{b=pm.response.json();}catch(e){}",
         "  if(Array.isArray(b)) tables=b.map(t=>typeof t==='string'?t:(t.name||t.tableName||'')).filter(t=>t);",
         "  else if(b.tables) tables=b.tables.map(t=>typeof t==='string'?t:(t.name||t.tableName||'')).filter(t=>t);",
         "  else tables=Object.keys(b).filter(k=>k!=='error'&&k!=='status');",
         "}",
         "const nodes=tables.slice(0,10).map((t,i)=>({id:'entity_'+i,label:t,type:'entity',prefix:'ds:',properties:{}}));",
         "pm.collectionVariables.set('_graphNodes', JSON.stringify(nodes));",
         "pm.collectionVariables.set('_graphLinks', '[]');",
         "console.log('Metadata: '+tables.slice(0,5).join(', ')+' -> '+nodes.length+' entities');"],
        base="transform_base_url",
        body={"driverType": "{{driverType}}", "dbHostName": "{{dbHost}}",
              "dbPort": "{{dbPort}}", "databaseName": "{{dbName}}",
              "dbUserName": "{{dbUser}}", "dbPassword": "{{dbPassword}}",
              "aesRandomIV": "{{aesRandomIV}}", "dbSchema": "{{dbSchema}}",
              "driverClassName": "{{driverClassName}}"})


def create_schema_step(step, name_prefix="pm-flow", base="app_base_url"):
    """Create schema."""
    return req(f"{step} Create Schema", "POST", "/schema",
        [f"const code=pm.response.code;",
         f"pm.test('{step} Schema 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.schemaModel||b.data||b;",
         "if(d.name||d.schemaName) pm.collectionVariables.set('schemaName', d.name||d.schemaName);",
         "if(d.id||d.schemaId) pm.collectionVariables.set('schemaId', String(d.id||d.schemaId));",
         "console.log('Schema: '+(d.name||d.schemaName));"],
        base=base,
        body={"schemaName": f"{name_prefix}-schema-" + "{{$timestamp}}",
              "description": "Auto-created by FLOW"})


def create_version_step(step, base="app_base_url"):
    """Create version with dataSourceIds and proper fields."""
    return req(f"{step} Create Version", "POST", "/versions/create?schemaName={{schemaName}}",
        [f"const code=pm.response.code;",
         f"pm.test('{step} Version 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.data||b;",
         "if(d.id||d.versionId) pm.collectionVariables.set('versionId', String(d.id||d.versionId));",
         "console.log('Version id='+(d.id||d.versionId));"],
        base=base, body={"versionName": "v1"},
        prerequest=[
            "const dsId=parseInt(pm.collectionVariables.get('dsId'));",
            "const ids=dsId&&!isNaN(dsId)?[dsId]:[];",
            "pm.request.body.raw=JSON.stringify({versionName:'v-'+Date.now(),description:'FLOW version',dataSourceIds:ids,defaultVersion:true,latest:true,versionLocked:false,deleted:false});",
        ])


def fetch_graph_step(step, base="app_base_url"):
    """Fetch DS graph and merge with existing nodes."""
    return req(f"{step} Fetch DS Graph", "POST", "/metadata-graph/fetch-data-source",
        [f"pm.test('{step} Graph 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201]));",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const newNodes=b.nodes||[]; const newLinks=b.links||[];",
         "let nodes=[]; try{nodes=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
         "let links=[]; try{links=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
         "nodes=nodes.concat(newNodes); links=links.concat(newLinks);",
         "pm.collectionVariables.set('_graphNodes', JSON.stringify(nodes));",
         "pm.collectionVariables.set('_graphLinks', JSON.stringify(links));",
         "console.log('DS graph: '+newNodes.length+' new, '+nodes.length+' total entities');"],
        base=base, body={"uri": "{{dataCatalogName}}"})


def save_graph_step(step, base="app_base_url"):
    """Save schema graph with all collected entities."""
    return req(f"{step} Save Schema Graph", "POST", "/schema-graph",
        [f"pm.test('{step} Graph saved 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,201,204]));",
         "console.log('Schema graph saved');"],
        base=base, body={"versionUri": "", "nodes": [], "links": []},
        prerequest=[
            "let nodes=[]; let links=[];",
            "try{nodes=JSON.parse(pm.collectionVariables.get('_graphNodes')||'[]');}catch(e){}",
            "try{links=JSON.parse(pm.collectionVariables.get('_graphLinks')||'[]');}catch(e){}",
            "console.log('Saving graph: '+nodes.length+' entities');",
            "pm.request.body.raw=JSON.stringify({versionUri:pm.collectionVariables.get('schemaName')+'Version#v',nodes:nodes,links:links,schemaName:pm.collectionVariables.get('schemaName')});",
        ])


def create_realm_step(step, name_prefix="pm-flow", base="app_base_url"):
    """Create realm with schemaName + versionId."""
    return req(f"{step} Create Realm", "POST", "/realm",
        [f"const code=pm.response.code;",
         f"pm.test('{step} Realm 2xx', () => {{ if(![200,201].includes(code)){{pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','{step}');}} pm.expect(code).to.be.oneOf([200,201]); }});",
         "let b={}; try{b=pm.response.json();}catch(e){}",
         "const d=b.realmModel||b.data||b;",
         "if(d.id||d.realmId) pm.collectionVariables.set('realmId', String(d.id||d.realmId));",
         "if(d.name||d.realmName) pm.collectionVariables.set('realmName', d.name||d.realmName);",
         "console.log('Realm id='+(d.id||d.realmId));"],
        base=base, body={"name": "x"},
        prerequest=[
            f"pm.request.body.raw=JSON.stringify({{name:'{name_prefix}-realm-'+Date.now(),description:'FLOW realm',schemaName:pm.collectionVariables.get('schemaName'),versionId:parseInt(pm.collectionVariables.get('versionId'))}});",
        ])


def full_setup_steps(step_prefix="01", name_prefix="pm-flow", include_realm=True, base="app_base_url"):
    """Full setup: DS → Metadata → Schema → Version → Graph → Realm.

    Returns list of steps. Step names: {prefix}a, {prefix}b, etc.
    """
    p = step_prefix
    steps = [
        create_ds_step(f"{p}a", base),
        fetch_metadata_step(f"{p}b"),
        create_schema_step(f"{p}c", name_prefix, base),
        create_version_step(f"{p}d", base),
        fetch_graph_step(f"{p}e", base),
        save_graph_step(f"{p}f", base),
    ]
    if include_realm:
        steps.append(create_realm_step(f"{p}g", name_prefix, base))
    return steps


def cleanup_steps(start_num=90, include_realm=True, base="app_base_url"):
    """Cleanup steps in reverse order."""
    steps = []
    n = start_num
    if include_realm:
        steps.append(req(f"{n} Del Realm", "DELETE", "/realm/{{realmId}}?permanent=true",
            [f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base))
        n += 1
    steps.append(req(f"{n} Del Graph", "DELETE", "/schema-graph?prefix={{schemaName}}",
        [f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base))
    n += 1
    steps.append(req(f"{n} Del Version", "DELETE", "/versions/delete?versionId={{versionId}}",
        [f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base))
    n += 1
    steps.append(req(f"{n} Del Schema", "DELETE", "/schema?schemaName={{schemaName}}",
        [f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"], base=base))
    n += 1
    steps.append(req(f"{n} Del DS", "DELETE", "/datasource/{{dsId}}",
        [f"pm.test('{n} ok', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));"], base=base))
    return steps


SETUP_VARS = [
    {"key": "dsId", "value": "", "type": "string"},
    {"key": "dataCatalogName", "value": "", "type": "string"},
    {"key": "schemaName", "value": "", "type": "string"},
    {"key": "schemaId", "value": "", "type": "string"},
    {"key": "versionId", "value": "", "type": "string"},
    {"key": "realmId", "value": "", "type": "string"},
    {"key": "realmName", "value": "", "type": "string"},
    {"key": "_graphNodes", "value": "", "type": "string"},
    {"key": "_graphLinks", "value": "", "type": "string"},
]

SETUP_CLEAR_VARS = ["dsId", "dataCatalogName", "schemaName", "schemaId",
                    "versionId", "realmId", "realmName", "_graphNodes", "_graphLinks"]
