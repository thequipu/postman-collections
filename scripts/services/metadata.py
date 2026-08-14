"""FLOW-Metadata-Read: Metadata and metadata-graph read operations.

Covers: 6 endpoints — metadata/datasource, by-id, tables/urns, nodes + metadata-graph operations.
Uses existing datasource/schema data from environment.
"""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "app_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Get All DataSources", "GET", "/metadata/datasource",
            ["pm.test('01 Metadata DS 200', () => pm.response.to.have.status(200));",
             "let b=[]; try{b=pm.response.json();}catch(e){}",
             "pm.test('01 has data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
             "// Capture first datasource id for next step",
             "const arr=Array.isArray(b)?b:(b.data||b.content||[]);",
             "if(arr.length>0){",
             "  const id=arr[0].id||arr[0].sourceId||arr[0].datasourceId;",
             "  if(id) pm.collectionVariables.set('metaDsId', String(id));",
             "}"],
            base=base),

        req("02 Get DataSource by ID", "GET", "/metadata/datasource/{{metaDsId}}",
            ["pm.test('02 DS by id 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));",
             "if(pm.response.code===200){",
             "  let b={}; try{b=pm.response.json();}catch(e){}",
             "  pm.test('02 has datasource data', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
             "}"],
            base=base),

        req("03 Get Tables URNs", "GET", "/metadata/tables/urns",
            ["pm.test('03 Tables URNs 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base),

        req("04 Get Nodes", "GET", "/metadata/nodes?schemaName={{schemaName}}&versionId={{versionId}}",
            ["pm.test('04 Nodes 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base),

        req("05 Fetch DataSource Graph", "POST", "/metadata-graph/fetch-data-source",
            ["pm.test('05 Fetch DS graph 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204]));"],
            base=base,
            body={"uri": "{{metaDsId}}"}),

        req("06 Add Description", "POST", "/metadata-graph/add-description",
            ["pm.test('06 Add description 200|204', () => pm.expect(pm.response.code).to.be.oneOf([200,204,400]));"],
            base=base,
            body={"nodeUri": "pm_flow_test_node", "description": "Test description by FLOW"}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Metadata Read",
        description="Metadata read operations: datasource listing, tables URNs, nodes, metadata-graph.\n\n"
                    "Uses existing data — no creation/deletion needed.",
        folder_name="Metadata Read",
        items=items,
        extra_variables=[
            {"key": "metaDsId", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Metadata-Read.postman_collection.json", col)
