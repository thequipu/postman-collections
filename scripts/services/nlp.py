"""FLOW-NLP-Pipeline: Stateless NLP service validation (no auth)."""

from flowlib.core import req, build_setup, build_teardown, build_collection, write_flow


def generate():
    base = "nlp_base_url"

    items = [
        # Custom setup — NLP uses /health not /actuator/health, and no auth
        {
            "name": "00 Setup",
            "event": [
                {"listen": "prerequest", "script": {"type": "text/javascript", "exec": [
                    "pm.collectionVariables.unset('_flow_failed');",
                    "pm.collectionVariables.unset('_flow_failed_at');",
                    "pm.collectionVariables.set('_skip_url', pm.environment.get('nlp_base_url') + '/health');",
                    "pm.collectionVariables.set('nlp_test_text', 'The quick brown fox jumps over the lazy dog.');",
                ]}},
                {"listen": "test", "script": {"type": "text/javascript", "exec": [
                    "pm.test('00 NLP service healthy', () => pm.response.to.have.status(200));",
                    "if(pm.response.code !== 200) {",
                    "  pm.collectionVariables.set('_flow_failed','true');",
                    "  pm.collectionVariables.set('_flow_failed_at','00 Setup');",
                    "}",
                ]}}
            ],
            "request": {
                "method": "GET", "header": [],
                "url": {"raw": "{{nlp_base_url}}/health", "host": ["{{nlp_base_url}}"], "path": ["health"]},
                "auth": {"type": "noauth"},
            },
            "response": []
        },

        req("01 Tokenize", "POST", "/tokenize",
            ["pm.test('01 Tokenize 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('01 has tokens', () => pm.expect(JSON.stringify(b).length).to.be.above(2));",
             "console.log('Tokens: '+JSON.stringify(b).slice(0,200));"],
            base=base, noauth=True,
            body={"text": "{{nlp_test_text}}"}),

        req("02 Sentenize", "POST", "/sentenize",
            ["pm.test('02 Sentenize 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('02 has sentences', () => pm.expect(JSON.stringify(b).length).to.be.above(2));"],
            base=base, noauth=True,
            body={"text": "{{nlp_test_text}}"}),

        req("03 Finalize Spans", "POST", "/finalize-spans",
            ["pm.test('03 Finalize spans 200', () => pm.expect(pm.response.code).to.be.oneOf([200,400]));"],
            base=base, noauth=True,
            body={"text": "{{nlp_test_text}}", "spans": []}),

        req("04 Embed", "POST", "/embed",
            ["pm.test('04 Embed 200', () => pm.response.to.have.status(200));",
             "let b={}; try{b=pm.response.json();}catch(e){}",
             "pm.test('04 has embeddings', () => pm.expect(JSON.stringify(b).length).to.be.above(10));",
             "console.log('Embed response keys: '+Object.keys(b||{}).join(', '));"],
            base=base, noauth=True,
            body={"texts": ["{{nlp_test_text}}"]}),

        # Teardown
        {
            "name": "99 Teardown",
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": [
                "pm.test('99 teardown', () => pm.response.to.have.status(200));",
                "pm.collectionVariables.unset('_flow_failed');",
                "pm.collectionVariables.unset('_flow_failed_at');",
            ]}}],
            "request": {
                "method": "GET", "header": [],
                "url": {"raw": "{{nlp_base_url}}/health", "host": ["{{nlp_base_url}}"], "path": ["health"]},
                "auth": {"type": "noauth"},
            },
            "response": []
        },
    ]

    col = build_collection(
        name="FLOW - NLP Pipeline",
        description="Stateless NLP service validation: tokenize, sentenize, finalize-spans, embed.\n\nNo auth required. Uses `{{nlp_base_url}}` (port 4055, direct).",
        folder_name="NLP Pipeline",
        items=items,
        extra_variables=[
            {"key": "nlp_test_text", "value": "The quick brown fox jumps over the lazy dog.", "type": "string"},
        ]
    )
    return write_flow("FLOW-NLP-Pipeline.postman_collection.json", col)
