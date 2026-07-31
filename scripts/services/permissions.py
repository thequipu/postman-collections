"""FLOW-Permissions-CRUD: Read-only RBAC validation."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Get Permissions", "GET", "/permissions",
            ["pm.test('01 Permissions 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('01 is array', () => pm.expect(Array.isArray(b)).to.be.true);"],
            base=base),

        req("02 Get Roles", "GET", "/roles",
            ["pm.test('02 Roles 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("03 Get Role Permissions", "GET", "/role-permission?page=0&size=20",
            ["pm.test('03 Role perms 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("04 Get User Permissions", "GET", "/user-permission?page=0&size=20",
            ["pm.test('04 User perms 200', () => pm.response.to.have.status(200));"],
            base=base),

        req("05 Get Entity360 Paths", "GET", "/user-permission/entity360-paths",
            ["pm.test('05 Entity360 paths 200', () => pm.response.to.have.status(200));"],
            base=base),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Permissions CRUD (Read-Only)",
        description="Read-only validation of RBAC endpoints: permissions, roles, user-permissions, entity360-paths.",
        folder_name="Permissions CRUD",
        items=items,
    )
    return write_flow("FLOW-Permissions-CRUD.postman_collection.json", col)
