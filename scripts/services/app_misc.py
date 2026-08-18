"""FLOW-App-Misc: Miscellaneous app-service endpoints.

Covers: tenant-specific, knowledgeGraph, neSolrStatus, entity-resolution-s3.
"""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Tenant Specific", "GET", "/tenant-specific",
            ["pm.test('01 Tenant specific 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('01 has data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base),

        req("02 Knowledge Graph", "GET", "/knowledgeGraph?page=0&size=20",
            ["pm.test('02 KG 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("03 NE Status All", "GET", "/neSolrStatus",
            ["pm.test('03 NE status 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("04 NE by Entity", "GET", "/neSolrStatus/named-entity-status?namedEntity=test",
            ["pm.test('04 NE by entity 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("05 NE Recent", "GET", "/neSolrStatus/recent-named-entity-status?namedEntity=test",
            ["pm.test('05 NE recent 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("06 NE Recent All", "GET", "/neSolrStatus/recent?realmName={{realm}}",
            ["pm.test('06 NE recent all 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("07 S3 Get Files", "POST", "/entity-resolution-s3/get-files",
            ["pm.test('07 S3 get files 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"folder": "pm_flow_test"}),

        req("08 S3 Get CSV Header", "POST", "/entity-resolution-s3/getCsvHeader",
            ["pm.test('08 S3 csv header 200|204|400', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"fileName": "pm_flow_test.csv"}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - App Misc",
        description="Miscellaneous app-service endpoints: tenant-specific, knowledge graph, NE status, S3 file ops.",
        folder_name="App Misc",
        items=items,
    )
    return write_flow("FLOW-App-Misc.postman_collection.json", col)
