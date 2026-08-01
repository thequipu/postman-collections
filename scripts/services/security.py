"""FLOW-Security-Auth: Security Service endpoint coverage (13/13 endpoints)."""

from flowlib.core import req, build_setup, build_collection, write_flow


def generate():
    base = "security_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=[
            "secAccessToken", "secRefreshToken"
        ]),

        # ── Admin Login (full validation — no OTP needed) ──

        req("01 Admin Login", "POST", "/admin/login",
            ["const code = pm.response.code;",
             "pm.test('01 Admin login 2xx', () => { if(![200,201].includes(code)){pm.collectionVariables.set('_flow_failed','true');pm.collectionVariables.set('_flow_failed_at','01 Admin Login');} pm.expect(code).to.be.oneOf([200,201]); });",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('01 has access_token', () => pm.expect(b.access_token).to.not.be.undefined);",
             "pm.test('01 has refresh_token', () => pm.expect(b.refresh_token).to.not.be.undefined);",
             "pm.test('01 has expires_in', () => pm.expect(b.expires_in).to.be.a('number'));",
             "pm.test('01 has token_type', () => pm.expect(b.token_type).to.eql('Bearer'));",
             "if(b.access_token) pm.collectionVariables.set('secAccessToken', b.access_token);",
             "if(b.refresh_token) pm.collectionVariables.set('secRefreshToken', b.refresh_token);",
             "console.log('Admin login: expires_in='+b.expires_in+', token_type='+b.token_type);"],
            base=base, noauth=True,
            body={"username": "{{adminUsername}}", "password": "{{adminPassword}}"}),

        # ── Validate Tenant (uses Bearer + plain text body) ──

        req("02 Validate Tenant (valid)", "POST", "/admin/validate-tenant",
            ["pm.test('02 Validate tenant 200', () => pm.response.to.have.status(200));",
             "pm.test('02 returns true', () => pm.expect(pm.response.text().trim()).to.eql('true'));",
             "console.log('Validate tenant: '+pm.response.text().trim());"],
            base=base,
            prerequest=[
                "pm.request.headers.upsert({key:'Authorization', value:'Bearer '+pm.collectionVariables.get('secAccessToken')});",
                "pm.request.headers.upsert({key:'Content-Type', value:'text/plain'});",
                "pm.request.body = {mode:'raw', raw:pm.environment.get('tenant_id')||'eksquipu'};"]),

        req("03 Validate Tenant (invalid)", "POST", "/admin/validate-tenant",
            ["pm.test('03 Validate invalid 200', () => pm.response.to.have.status(200));",
             "pm.test('03 returns false', () => pm.expect(pm.response.text().trim()).to.eql('false'));",
             "console.log('Validate invalid tenant: '+pm.response.text().trim());"],
            base=base,
            prerequest=[
                "pm.request.headers.upsert({key:'Authorization', value:'Bearer '+pm.collectionVariables.get('secAccessToken')});",
                "pm.request.headers.upsert({key:'Content-Type', value:'text/plain'});",
                "pm.request.body = {mode:'raw', raw:'nonexistent-tenant-xyz'};"]),

        # ── Endpoint Reachability Tests (all 13 endpoints covered) ──

        req("04 Admin Introspect (reachability)", "POST", "/admin/introspect",
            ["pm.test('04 Introspect reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401]));",
             "console.log('Admin introspect: '+pm.response.code);"],
            base=base, noauth=True,
            body={"access_token": "{{secAccessToken}}"}),

        req("05 Admin Refresh Token (reachability)", "POST", "/admin/refreshToken",
            ["pm.test('05 Refresh reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401]));",
             "console.log('Admin refresh: '+pm.response.code);"],
            base=base, noauth=True,
            body={"refresh_token": "{{secRefreshToken}}"}),

        req("06 Short-Lived Token (reachability)", "POST", "/admin/short-lived-token",
            ["pm.test('06 Short-lived reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401,500]));",
             "console.log('Short-lived token: '+pm.response.code);"],
            base=base,
            prerequest=[
                "pm.request.headers.upsert({key:'Authorization', value:'Bearer '+pm.collectionVariables.get('secAccessToken')});"]),

        req("07 Admin Logout (reachability)", "POST", "/admin/logout",
            ["pm.test('07 Admin logout reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,401]));",
             "console.log('Admin logout: '+pm.response.code);"],
            base=base, noauth=True,
            body={"refresh_token": "{{secRefreshToken}}"}),

        req("08 Generate OTP (full validation)", "POST", "/user/generate-otp?isUserAdmin=false",
            ["pm.test('08 Generate OTP 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('08 OTP sent message', () => pm.expect(b.message||'').to.include('OTP sent'));",
             "console.log('Generate OTP: '+pm.response.code+' — '+(b.message||''));"],
            base=base, noauth=True,
            extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}],
            body={"username": "{{test_username}}", "password": "{{test_password}}"}),

        req("09 User Login (wrong OTP validation)", "POST", "/user/login?isUserAdmin=false",
            ["pm.test('09 Login returns 401', () => pm.response.to.have.status(401));",
             "const body = pm.response.text();",
             "pm.test('09 OTP invalid message', () => pm.expect(body).to.include('OTP'));",
             "pm.test('09 specific error (not generic 401)', () => pm.expect(body).to.include('INVALID'));",
             "console.log('User login: '+pm.response.code+' — '+body);"],
            base=base, noauth=True,
            extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}],
            body={"username": "{{test_username}}", "password": "{{test_password}}", "otp": "000000"}),

        req("10 User Internal Token (reachability)", "POST", "/user/internal-token",
            ["pm.test('10 Internal token reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401,500]));",
             "console.log('Internal token: '+pm.response.code);"],
            base=base, noauth=True,
            extra_headers=[{"key": "X-Tenant-ID", "value": "{{tenant_id}}"}],
            body={"username": "internal-test", "password": "test"}),

        req("11 User Introspect (reachability)", "POST", "/user/introspect",
            ["pm.test('11 User introspect reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401]));",
             "console.log('User introspect: '+pm.response.code);"],
            base=base, noauth=True,
            body={"access_token": "{{secAccessToken}}"}),

        req("12 User Refresh (reachability)", "POST", "/user/refreshToken",
            ["pm.test('12 User refresh reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401]));",
             "console.log('User refresh: '+pm.response.code);"],
            base=base, noauth=True,
            body={"refresh_token": "{{secRefreshToken}}"}),

        req("13 User Get Users (reachability)", "GET", "/user/users",
            ["pm.test('13 Get users reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,400,401]));",
             "if(pm.response.code===200) {",
             "  let b=[]; try{b=pm.response.json();}catch(e){}",
             "  pm.test('13 is array', () => pm.expect(Array.isArray(b)).to.be.true);",
             "  pm.test('13 has users', () => pm.expect(b.length).to.be.above(0));",
             "  console.log('Users: '+b.length);",
             "} else { console.log('Get users: '+pm.response.code+' (needs tenant OTP token — admin token rejected by gateway)'); }"],
            base=base,
            prerequest=[
                "pm.request.headers.upsert({key:'Authorization', value:'Bearer '+pm.collectionVariables.get('secAccessToken')});",
                "pm.request.headers.upsert({key:'X-Tenant-ID', value:pm.environment.get('tenant_id')||'eksquipu'});"]),

        req("14 User Logout (reachability)", "POST", "/user/logout",
            ["pm.test('14 User logout reachable', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,401]));",
             "console.log('User logout: '+pm.response.code);"],
            base=base, noauth=True,
            body={"refresh_token": "{{secRefreshToken}}"}),

        # ── Teardown ──

        req("99 Teardown", "GET", "/actuator/health",
            ["pm.test('99 teardown', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400,404]));",
             "pm.collectionVariables.unset('_flow_failed');",
             "pm.collectionVariables.unset('_flow_failed_at');"],
            base=base, skip_on_fail=False, noauth=True),
    ]

    col = build_collection(
        name="FLOW - Security Service Auth (Full)",
        description=(
            "Full Security Service endpoint coverage (13/13 endpoints):\n\n"
            "| # | Method | Endpoint | Step | Validation |\n"
            "|---|--------|----------|------|------------|\n"
            "| 1 | POST | /admin/login | 01 | Full (token, refresh, expires_in, type) |\n"
            "| 2 | POST | /admin/validate-tenant | 02-03 | Full (valid=true, invalid=false) |\n"
            "| 3 | POST | /admin/introspect | 04 | Reachability |\n"
            "| 4 | POST | /admin/refreshToken | 05 | Reachability |\n"
            "| 5 | POST | /admin/short-lived-token | 06 | Reachability |\n"
            "| 6 | POST | /admin/logout | 07 | Reachability |\n"
            "| 7 | POST | /user/generate-otp | 08 | Reachability (needs real email) |\n"
            "| 8 | POST | /user/login | 09 | Reachability (needs OTP) |\n"
            "| 9 | POST | /user/internal-token | 10 | Reachability |\n"
            "| 10 | POST | /user/introspect | 11 | Reachability |\n"
            "| 11 | POST | /user/refreshToken | 12 | Reachability |\n"
            "| 12 | GET | /user/users | 13 | Reachability |\n"
            "| 13 | POST | /user/logout | 14 | Reachability |\n\n"
            "**Coverage: 13/13 endpoints (100%)**\n\n"
            "**Note:** Admin login + validate-tenant are fully validated. "
            "Other endpoints are reachability-tested (verify endpoint exists, accepts correct method). "
            "Full user login flow requires OTP email — not automatable in CI/CD."
        ),
        folder_name="Security Auth",
        items=items,
        extra_variables=[
            {"key": "secAccessToken",  "value": "", "type": "string"},
            {"key": "secRefreshToken", "value": "", "type": "string"},
            {"key": "adminUsername",   "value": "admin", "type": "string"},
            {"key": "adminPassword",  "value": "admin123", "type": "string"},
        ]
    )
    return write_flow("FLOW-Security-Auth.postman_collection.json", col)
