"""GPT-5.4 mini Copilot: real-provider request contract, privacy and billing safeguards.

Network calls are intentionally mocked; real OpenAI credentials are never required in CI.
"""
import sqlite3

import ceyrl_ai
from test_v5 import app_clients, signup, event, ticket


def ai_response(answer="The 2026 FIFA World Cup started on 11 June 2026.", web=True,
                input_tokens=800, output_tokens=180):
    output=[]
    if web:
        output.append({"type":"web_search_call","action":{"sources":[{
          "url":"https://www.fifa.com/","title":"FIFA"
        }]}})
    output.append({"type":"message","content":[{"type":"output_text","text":answer,
       "annotations":[{"type":"url_citation","url":"https://www.fifa.com/","title":"FIFA"}] if web else []}]})
    return {"output":output,"usage":{"input_tokens":input_tokens,"output_tokens":output_tokens}}


def test_online_mini_requires_key_and_offline_never_pretends_general_knowledge(app_clients):
    _,alice,_,_=app_clients
    csrf=signup(alice,"mini-unconfigured@example.com","Mini User")
    status=alice.get("/api/x/copilot/status").json()
    assert status["model"]=="gpt-5.4-mini"
    assert status["configured"] is False
    blocked=alice.post("/api/x/copilot",headers={"x-csrf-token":csrf},
        json={"question":"When is World Cup?","use_ai":True})
    assert blocked.status_code==503
    assert "CTW_OPENAI_API_KEY" in blocked.text
    offline=alice.post("/api/x/copilot",headers={"x-csrf-token":csrf},
        json={"question":"When is World Cup?","use_ai":False})
    assert offline.status_code==200
    assert "cannot answer general questions" in offline.json()["answer"]
    assert offline.json()["mode"]=="local"
    assert alice.get("/api/x/copilot/history").json()["messages"]==[]


def test_gpt54_mini_source_citations_encrypted_chat_and_followups(app_clients,monkeypatch):
    _,alice,bob,persistent=app_clients
    token=signup(alice,"mini-alice@example.com","Mini Alice")
    signup(bob,"mini-bob@example.com","Mini Bob")
    event_id=event(alice,token,"Secret Alice Festival")
    ticket(alice,token,event_id)
    monkeypatch.setenv("CTW_OPENAI_API_KEY","sk-testing-only-do-not-use")
    calls=[]
    def fake(key,payload):
        assert key=="sk-testing-only-do-not-use"
        calls.append(payload)
        return ai_response(web=len(calls)==1,answer=(
            "The football World Cup was in June 2026." if len(calls)==1
            else "That is the men's football tournament."))
    monkeypatch.setattr(ceyrl_ai,"request_openai",fake)

    state=alice.get("/api/x/copilot/status").json()
    assert state["configured"] is True
    assert state["web_available"] is True
    first=alice.post("/api/x/copilot",headers={"x-csrf-token":token},json={
        "question":"When was the World Cup?","use_ai":True,
        "web_search":True,"include_inventory":False
    })
    assert first.status_code==200,first.text
    assert first.json()["mode"]=="ai"
    assert first.json()["model"]=="gpt-5.4-mini"
    assert first.json()["web_used"] is True
    assert first.json()["citations"][0]["url"]=="https://www.fifa.com/"
    assert calls[0]["model"]=="gpt-5.4-mini"
    assert calls[0]["store"] is False
    assert calls[0]["max_tool_calls"]==1
    assert calls[0]["tools"]==[{"type":"web_search","search_context_size":"low"}]
    assert "Secret Alice Festival" not in str(calls[0]["input"])

    follow=alice.post("/api/x/copilot",headers={"x-csrf-token":token},json={
        "question":"Which sport did we discuss?","use_ai":True,
        "web_search":False,"include_inventory":True
    })
    assert follow.status_code==200,follow.text
    assert calls[1]["model"]=="gpt-5.4-mini"
    assert "tools" not in calls[1]
    assert "Secret Alice Festival" in str(calls[1]["input"])
    assert any(x.get("content")=="When was the World Cup?" for x in calls[1]["input"])
    assert any(x.get("content")=="The football World Cup was in June 2026."
               for x in calls[1]["input"])

    history=alice.get("/api/x/copilot/history")
    assert history.status_code==200
    assert len(history.json()["messages"])==4
    assert bob.get("/api/x/copilot/history").json()["messages"]==[]

    mine=alice.get("/api/auth/state").json()["user"]["id"]
    path=persistent/"users"/mine/"inventory.sqlite3"
    with sqlite3.connect(path) as db:
        values=[row[0] for row in db.execute("SELECT ciphertext FROM x_ai_messages")]
        assert values and all(b"World Cup" not in raw for raw in values)
        assert all(b"Secret Alice Festival" not in raw for raw in values)
    budget=alice.get("/api/x/copilot/status").json()
    assert budget["estimated_account_usage_usd"] > 0

    assert alice.delete("/api/x/copilot/history").status_code==403
    clear=alice.delete("/api/x/copilot/history",headers={"x-csrf-token":token})
    assert clear.status_code==200,clear.text
    assert alice.get("/api/x/copilot/history").json()["messages"]==[]
    assert bob.get("/api/x/copilot/history").json()["messages"]==[]


def test_server_estimated_monthly_usage_guard(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    token=signup(alice,"budget-test@example.com","Budget test")
    monkeypatch.setenv("CTW_OPENAI_API_KEY","sk-budget-test")
    monkeypatch.setenv("CTW_OPENAI_MONTHLY_LIMIT_USD","0.5")
    count=[]
    def costly_call(key,payload):
        count.append(True)
        return ai_response("Budget charged.",web=False,input_tokens=1_000_000,output_tokens=120)
    monkeypatch.setattr(ceyrl_ai,"request_openai",costly_call)
    question={"question":"What are my recorded sales?","use_ai":True}
    first=alice.post("/api/x/copilot",json=question,headers={"x-csrf-token":token})
    assert first.status_code==200,first.text
    second=alice.post("/api/x/copilot",json=question,headers={"x-csrf-token":token})
    assert second.status_code==429
    assert len(count)==1


def test_untrusted_source_url_is_not_accepted(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    token=signup(alice,"web-safe@example.com","Safe user")
    monkeypatch.setenv("CTW_OPENAI_API_KEY","sk-safe-test")
    def provider(key,payload):
        return {"output":[{"type":"message","content":[{
          "type":"output_text","text":"A safe answer.",
          "annotations":[{"type":"url_citation","url":"javascript:alert(1)","title":"Malicious"},
                         {"type":"url_citation","url":"https://example.com/events","title":"Source"}]
        }]}],"usage":{"input_tokens":200,"output_tokens":30}}
    monkeypatch.setattr(ceyrl_ai,"request_openai",provider)
    res=alice.post("/api/x/copilot",json={"question":"What is next?", "use_ai":True},
                   headers={"x-csrf-token":token})
    assert res.status_code==200,res.text
    assert res.json()["citations"]==[{"url":"https://example.com/events","title":"Source"}]
