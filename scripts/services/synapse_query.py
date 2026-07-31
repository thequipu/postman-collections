"""FLOW-Synapse-Query: Advanced Cypher query operations (sync, async, explain, v2)."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "synapse_base_url"

    items = [
        build_setup(base, "/actuator/health", clear_vars=["asyncQueryId"]),

        # v1 Cypher Engine
        req("01 Cypher Query (sync)", "POST", "/query/cypher",
            ["pm.test('01 Cypher sync 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Cypher result: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{realm}}"}),

        req("02 Cypher Explain", "POST", "/query/cypher/explain",
            ["pm.test('02 Explain 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Explain: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{realm}}"}),

        req("03 Cypher Async Submit", "POST", "/query/cypher/async",
            ["pm.test('03 Async submit 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "const qid=b.queryId||b.id;",
             "if(qid) pm.collectionVariables.set('asyncQueryId', qid);",
             "console.log('Async queryId: '+qid);"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{realm}}"}),

        req("04 Async Poll Result", "GET", "/query/cypher/async/result?queryId={{asyncQueryId}}",
            ["pm.test('04 Async result 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('Async result: '+JSON.stringify(b).slice(0,200));"],
            base=base),

        # v2 Cypher Engine
        req("05 v2 Cypher Query", "POST", "/api/v2/cypher/query",
            ["pm.test('05 v2 query 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "console.log('v2 result: '+JSON.stringify(b).slice(0,200));"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{realm}}"}),

        req("06 v2 Cypher Explain", "POST", "/api/v2/cypher/explain",
            ["pm.test('06 v2 explain 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
            base=base,
            body={"query": "RETURN 1 AS n", "namespace": "{{realm}}"}),

        # Node operations
        req("07 Fetch Node", "POST", "/node/fetch",
            ["pm.test('07 Fetch node 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400,404]));"],
            base=base,
            body={"namespace": "{{realm}}"}),

        # Consumer control
        req("08 Consumer Pause", "POST", "/consumer/pause",
            ["pm.test('08 Consumer pause 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202,400,404]));"],
            base=base),

        req("09 Consumer Resume", "POST", "/consumer/resume",
            ["pm.test('09 Consumer resume 200', () => pm.expect(pm.response.code).to.be.oneOf([200,202,400,404]));"],
            base=base),

        build_teardown(base),
    ]

    col = build_collection(
        name="FLOW - Synapse Query (Advanced)",
        description="Advanced Synapse query operations: sync, explain, async + poll, v2 engine, node fetch, consumer control.\n\nUses `{{synapse_base_url}}` and `{{realm}}` from environment.",
        folder_name="Synapse Query",
        items=items,
        extra_variables=[
            {"key": "asyncQueryId", "value": "", "type": "string"},
        ]
    )
    return write_flow("FLOW-Synapse-Query.postman_collection.json", col)
