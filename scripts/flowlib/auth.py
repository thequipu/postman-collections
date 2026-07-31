"""Keycloak auth pre-request script and destructive-verb guard."""


def keycloak_prerequest():
    """Collection-level pre-request JS: auto-refresh Keycloak token with 60s cache."""
    return [
        "const destructive=['POST','PUT','PATCH','DELETE'];",
        "if(pm.environment.get('allow_destructive')==='false' && destructive.includes(pm.request.method)){",
        "  throw new Error('Blocked '+pm.request.method+' in env='+pm.environment.get('env_name'));",
        "}",
        "const url=pm.environment.get('keycloak_token_url'); const user=pm.environment.get('test_username');",
        "if(!url||!user){ return; }",
        "const tok=pm.collectionVariables.get('access_token'); const exp=pm.collectionVariables.get('token_expiry');",
        "if(tok && exp && Date.now() < Number(exp)-60000){ return; }",
        "pm.sendRequest({url:url,method:'POST',header:{'Content-Type':'application/x-www-form-urlencoded'},",
        "  body:{mode:'urlencoded',urlencoded:[",
        "    {key:'grant_type',value:'password'},{key:'client_id',value:pm.environment.get('client_id')},",
        "    {key:'client_secret',value:pm.environment.get('client_secret')},",
        "    {key:'username',value:pm.environment.get('test_username')},{key:'password',value:pm.environment.get('test_password')}]}},",
        "  (e,res)=>{ if(e||res.code!==200){ throw new Error('token fetch failed: '+(e||res.status)); }",
        "    const b=res.json(); pm.collectionVariables.set('access_token',b.access_token);",
        "    pm.collectionVariables.set('token_expiry', Date.now()+b.expires_in*1000);",
        "    pm.environment.set('access_token', b.access_token); });",
    ]
