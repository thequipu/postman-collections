"""FLOW-Lumen-Pipeline: Lumen AI pipeline validation."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "lumen_base_url"

    items = [
        build_setup(base, "/actuator/health"),

        req("01 Query Builder", "POST", "/query-builder/query",
            ["pm.test('01 Query builder 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "if(pm.response.code===200) console.log('Generated query: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"realm": "{{realm}}", "question": "Show all entities"}),

        req("02 Reset Schema", "POST", "/query-builder/reset-schema",
            ["pm.test('02 Reset schema 2xx', () => pm.expect(pm.response.code).to.be.oneOf([200,204,404]));"],
            base=base,
            body={"realm": "{{realm}}"}),

        req("03 Describe Datasource", "POST", "/lumen/describe/datasource",
            ["pm.test('03 Describe 2xx or 400', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Describe response: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"versionUri": "{{versionUri}}", "overwrite": False}),

        req("04 Embed Datasource", "POST", "/lumen/embed/datasource",
            ["pm.test('04 Embed 2xx or 400', () => pm.expect(pm.response.code).to.be.oneOf([200,201,400,404]));"],
            base=base,
            body={"versionUri": "{{versionUri}}", "overwrite": False}),

        req("05 Cluster Preview", "POST", "/lumen/cluster/final-clusters",
            ["pm.test('05 Clusters 2xx or 400', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "if(b.clusters) console.log('Clusters: '+b.clusters.length);"],
            base=base,
            body={"versionUri": "{{versionUri}}"}),

        req("06 Semantic Chat", "POST", "/semantic-chat/getAnswer",
            ["pm.test('06 Semantic chat 2xx or 400', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
            base=base,
            body={"messageContextModels": [
                {"role": "system", "content": "You are a data analyst. Data: [{'id':1,'name':'test'}]"},
                {"role": "user", "content": "What is in the data?"}
            ]}),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Lumen Pipeline",
        description="Lumen AI pipeline: query-builder, describe, embed, cluster, semantic-chat.\n\nSteps 03-05 require `--env-var versionUri=...` for a valid schema version.\nSteps 01-02 require `{{realm}}` from environment.",
        folder_name="Lumen Pipeline",
        items=items,
        extra_variables=[
            {"key": "versionUri", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Lumen-Pipeline.postman_collection.json", col)
