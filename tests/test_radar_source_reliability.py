"""Event Radar reliability after real HTTP probes (Gigora=402, StungEvents=410).

Tests cover server-owned Ticketmaster access, honest limited keyless mode and
isolated explicit imports. External provider calls are always mocked in CI.
"""
from fastapi import HTTPException
import ceyrl_features
import ceyrl_radar
from test_v5 import app_clients, signup


MOCK_TM={
    "id":"tmCALIN2027","name":"Calin — concert",
    "dates":{"start":{"dateTime":"2027-04-20T19:00:00Z",
                       "localDate":"2027-04-20"}},
    "_embedded":{"venues":[{"name":"Sample Venue","city":{"name":"Prague"},
                             "country":{"name":"Czech Republic"}}]},
    "url":"https://www.ticketmaster.com/event/tmCALIN2027",
    "classifications":[{"segment":{"name":"Music"}}],
}


def test_keyless_mode_explicitly_limits_catalog_for_calins_concert(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"ticketmaster-no-key@example.com","No shared key")
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.delenv("TICKETMASTER_API_KEY",raising=False)
    checked=[]
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:
        (checked.append((q,c)) or []))
    status=alice.get("/api/x/radar/status").json()
    assert status["connected"] is True
    assert status["key_required"] is False
    assert status["global_concerts_enabled"] is False
    assert "Ticket Fairy" in status["provider"]
    assert "Gigora" not in str(status)
    assert "StungEvents" not in str(status)

    result=alice.get("/api/x/radar/search?q=Calin&kind=music")
    assert result.status_code==200,result.text
    data=result.json()
    assert data["events"]==[]
    assert data["requires_server_key"] is True
    assert data["sources_checked"]==["Ticket Fairy"]
    assert "CTW_TICKETMASTER_API_KEY" in data["coverage_note"]
    assert checked==[("Calin","")]


def test_one_shared_server_key_searches_calins_concert_for_every_user(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    ca=signup(alice,"shared-a@example.com","Shared A")
    signup(bob,"shared-b@example.com","Shared B")
    monkeypatch.setenv("CTW_TICKETMASTER_API_KEY","SharedServerKeyInEnvironment")
    monkeypatch.delenv("TICKETMASTER_API_KEY",raising=False)
    # Even a user's stale personal key must not override the shared server key.
    stored=alice.put("/api/x/radar/key",
        json={"api_key":"OldUserKeyThatIsNotValid123"},
        headers={"x-csrf-token":ca})
    assert stored.status_code==200,stored.text
    external=[]
    def tm(key,params,one_id=None):
        assert key=="SharedServerKeyInEnvironment"
        external.append((params,one_id))
        if one_id:
            assert one_id=="tmCALIN2027"
            return MOCK_TM
        assert params["keyword"]=="Calin"
        return {"_embedded":{"events":[MOCK_TM]}}
    monkeypatch.setattr(ceyrl_features,"call_tm",tm)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:
        (_ for _ in ()).throw(AssertionError("Do not call backup on successful Ticketmaster search")))

    for client in (alice,bob):
        status=client.get("/api/x/radar/status").json()
        assert status["server_ticketmaster"] is True
        assert status["global_concerts_enabled"] is True
        assert "Ticketmaster" in status["provider"]
        response=client.get("/api/x/radar/search?q=Calin&kind=music")
        assert response.status_code==200,response.text
        result=response.json()
        assert result["requires_server_key"] is False
        assert result["provider_warnings"]==[]
        assert result["sources_checked"]==["Ticketmaster"]
        assert result["events"][0]["name"]=="Calin — concert"
        assert result["events"][0]["provider"]=="Ticketmaster"

    assert alice.get("/api/events").json()==[]
    imported=alice.post("/api/x/radar/import/tmCALIN2027",
                        headers={"x-csrf-token":ca})
    assert imported.status_code==200,imported.text
    assert alice.get("/api/events").json()[0]["title"]=="Calin — concert"
    assert bob.get("/api/events").json()==[]
    assert len(external)==3


def test_failed_shared_key_not_misrepresented_as_no_concert(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"shared-fail@example.com","Invalid shared key")
    monkeypatch.setenv("CTW_TICKETMASTER_API_KEY","InvalidKeyInEnvironment")
    monkeypatch.setattr(ceyrl_features,"call_tm",lambda *args,**kwargs:
        (_ for _ in ()).throw(HTTPException(403,"Provider rejected key")))
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    response=alice.get("/api/x/radar/search?q=Calin&kind=music")
    assert response.status_code==200,response.text
    payload=response.json()
    assert payload["events"]==[]
    assert payload["partial_outage"] is True
    assert payload["provider_warnings"]
    assert "Ticketmaster" in payload["provider_warnings"][0]
    assert payload["sources_checked"]==["Ticket Fairy"]
    assert "Gigora" not in str(payload)
    assert "StungEvents" not in str(payload)


def test_removed_provider_sources_are_not_accepted_for_new_imports(app_clients):
    _,alice,_,_=app_clients
    csrf=signup(alice,"old-import@example.com","Old import")
    # Previously created events remain in the user's inventory, but newly
    # expired source records cannot be imported through removed providers.
    for key in ("gi:abcdefabcdefabcdefabcdefab",
                "se:old-gigora-concert", "td:OLDFAKESOURCE1"):
        r=alice.post("/api/x/radar/import/"+key,headers={"x-csrf-token":csrf})
        assert r.status_code in (404,422)
