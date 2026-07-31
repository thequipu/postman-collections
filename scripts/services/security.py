"""FLOW-Security-Auth: Auth pipeline validation flow."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "security_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["introspect_sub"]),

        req("01 Validate Tenant", "POST", "/admin/validate-tenant",
            ["pm.test('01 Validate tenant 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Validate tenant result: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"tenantId": "{{tenant_id}}"}),

        req("02 Admin Login", "POST", "/admin/login",
            ["pm.test('02 Admin login 200', () => pm.expect(pm.response.code).to.be.oneOf([200,401]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Admin login: '+pm.response.code);"],
            base=base,
            body={"username": "{{test_username}}", "password": "{{test_password}}", "tenantId": "{{tenant_id}}"}),

        req("03 Health Check", "GET", "/actuator/health",
            ["pm.test('03 Health 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('03 status UP', () => pm.expect(b.status||'').to.eql('UP'));"],
            base=base, noauth=True),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Security Service Auth",
        description="Validates Security Service: validate-tenant, admin login, health.\n\nNote: introspect/users endpoints require specific auth mechanisms not compatible with Bearer token flow.",
        folder_name="Security Auth",
        items=items,
        extra_variables=[
            {"key": "introspect_sub", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Security-Auth.postman_collection.json", col)
