"""Regression tests for keyless Event Radar, Magic Inbox removal and auth hardening."""
import io
import sqlite3
from datetime import datetime, timezone, timedelta

import ceyrl_radar
from test_v5 import app_clients, signup


PUBLIC_EVENT={
  "url":"https://www.ticketfairy.com/event/moonlight-festival",
  "displayName":"Moonlight Festival",
  "startDate":"2027-07-15T20:00:00+02:00",
  "venue":{"name":"Open Air Park","city":"Bratislava","country":"sk"}
}


def test_keyless_radar_search_is_scoped_and_imports_only_sourced_results(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    token_a=signup(alice,"keyless-a@example.com","Keyless A")
    token_b=signup(bob,"keyless-b@example.com","Keyless B")
    hits=[]
    def fake_public(query,country):
        hits.append((query,country))
        return [ceyrl_radar.normalize_public_event(PUBLIC_EVENT)]
    monkeypatch.setattr(ceyrl_radar,"request_public",fake_public)

    anon=alice.get("/api/x/radar/status")
    assert anon.status_code==200
    assert anon.json()["connected"] is True
    assert anon.json()["key_required"] is False
    assert not anon.json()["personal_key"]

    result=alice.get("/api/x/radar/search?q=Moonlight&country=SK")
    assert result.status_code==200,result.text
    assert "Ticket Fairy" in result.json()["source"]
    events=result.json()["events"]
    assert len(events)==1
    evt=events[0]
    assert evt["id"]=="tf:moonlight-festival"
    assert evt["local_date"]=="2027-07-15"
    assert evt["starts_at"]=="2027-07-15T18:00:00+00:00"
    assert evt["provider"]=="Ticket Fairy"
    assert evt["url"]==PUBLIC_EVENT["url"]
    assert hits==[("Moonlight","SK")]
    # Repeated search within cache TTL should not repeat third-party call.
    second=alice.get("/api/x/radar/search?q=Moonlight&country=SK")
    assert second.status_code==200 and hits==[("Moonlight","SK")]
    assert bob.get("/api/x/radar/import/tf:moonlight-festival").status_code==405
    assert bob.post("/api/x/radar/import/tf:moonlight-festival",
                    headers={"x-csrf-token":token_b}).status_code==404
    assert alice.post("/api/x/radar/import/tf:moonlight-festival").status_code==403
    imported=alice.post("/api/x/radar/import/tf:moonlight-festival",
                       headers={"x-csrf-token":token_a})
    assert imported.status_code==200,imported.text
    assert alice.get("/api/events").json()[0]["title"]=="Moonlight Festival"
    assert alice.get("/api/events").json()[0]["starts_at"].startswith("2027-07-15T18:00")
    assert not bob.get("/api/events").json()
    repeated=alice.post("/api/x/radar/import/tf:moonlight-festival",
                        headers={"x-csrf-token":token_a})
    assert repeated.status_code==200 and repeated.json()["already_exists"] is True
    assert len(alice.get("/api/events").json())==1


def test_keyless_watchlist_refresh_is_private(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    a=signup(alice,"keyless-watch-a@example.com","Watch A")
    signup(bob,"keyless-watch-b@example.com","Watch B")
    seen=[]
    def mock(query,country):
        seen.append((query,country))
        return [ceyrl_radar.normalize_public_event(PUBLIC_EVENT)]
    monkeypatch.setattr(ceyrl_radar,"request_public",mock)
    watch=alice.post("/api/x/radar/watches",headers={"x-csrf-token":a},
                     json={"query":"Moonlight Festival","country":"SK"})
    assert watch.status_code==200,watch.text
    first=alice.post("/api/x/radar/refresh",headers={"x-csrf-token":a})
    assert first.status_code==200,first.text
    assert first.json()["new"]==1
    assert len(alice.get("/api/x/radar/watches").json()["hits"])==1
    assert not bob.get("/api/x/radar/watches").json()["hits"]
    second=alice.post("/api/x/radar/refresh",headers={"x-csrf-token":a})
    assert second.status_code==200,second.text
    assert second.json()["skipped"]==1
    assert len(seen)==1


def test_untrusted_public_event_data_is_rejected():
    bad=[
      {**PUBLIC_EVENT,"url":"https://evil.example/event/moonlight-festival"},
      {**PUBLIC_EVENT,"url":"https://www.ticketfairy.com.evil.example/event/moonlight-festival"},
      {**PUBLIC_EVENT,"url":"javascript:alert(1)"},
      {**PUBLIC_EVENT,"url":"https://www.ticketfairy.com/event/../../admin"},
      {**PUBLIC_EVENT,"startDate":"2027-07-15T20:00:00"},
      {**PUBLIC_EVENT,"displayName":""}
    ]
    for row in bad:
        assert ceyrl_radar.normalize_public_event(row) is None
    expected=ceyrl_radar.normalize_public_event(PUBLIC_EVENT)
    assert expected["starts_at"].endswith("+00:00")


def test_radar_rejects_excessive_requests(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"ratelimit-radar@example.com","Rate Radar")
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    status=[]
    for x in range(21):
        result=alice.get("/api/x/radar/search?q=Music%20"+str(x)+"&country=")
        status.append(result.status_code)
    assert all(code==200 for code in status[:20])
    assert status[20]==429


def test_magic_inbox_is_no_longer_available_and_existing_data_remains_untouched(app_clients):
    m,alice,_,data=app_clients
    csrf=signup(alice,"no-magic@example.com","No Magic")
    assert alice.get("/api/inbox/settings").status_code==404
    assert alice.get("/api/inbox/drafts").status_code==404
    assert alice.post("/api/inbox/mailgun",data={}).status_code==404
    assert alice.post("/api/inbox/paste",headers={"x-csrf-token":csrf},
                      json={"subject":"test","body":"test"}).status_code==404
    document=alice.get("/").text
    assert "/static/inbox.js" not in document
    assert "/static/inbox.css" not in document
    assert "Magic Inbox" not in alice.get("/static/app.js").text
    # Previous tickets/other accounts remain usable.
    payload={"title":"Existing event", "starts_at":
        (datetime.now(timezone.utc)+timedelta(days=3)).isoformat()}
    saved=alice.post("/api/events",json=payload,headers={"x-csrf-token":csrf})
    assert saved.status_code==200
    assert alice.get("/api/events").json()[0]["title"]=="Existing event"


def test_security_headers_origin_guard_and_path_downloads(app_clients):
    m,alice,_,data=app_clients
    token=signup(alice,"secure-origin@example.com","Secure user")
    response=alice.get("/api/auth/state")
    headers=response.headers
    assert headers["referrer-policy"]=="no-referrer"
    assert headers["cross-origin-opener-policy"]=="same-origin"
    assert "geolocation=()" in headers["permissions-policy"]
    assert headers["x-content-type-options"]=="nosniff"
    from datetime import datetime,timezone,timedelta
    event_payload={"title":"Secure event", "starts_at":
        (datetime.now(timezone.utc)+timedelta(days=4)).isoformat()}
    attacker=alice.post("/api/events",json=event_payload,
                        headers={"origin":"https://evil.example","host":"evil.example",
                                 "x-csrf-token":token})
    assert attacker.status_code==403
    cross_site=alice.post("/api/events",json=event_payload,
                        headers={"sec-fetch-site":"cross-site","x-csrf-token":token})
    assert cross_site.status_code==403
    legitimate=alice.post("/api/events",json=event_payload,
                         headers={"x-csrf-token":token})
    assert legitimate.status_code==200,legitimate.text


def test_session_count_is_bounded_after_repeated_login(app_clients):
    m,alice,_,data=app_clients
    csrf=signup(alice,"sessions@example.com","Sessions Owner")
    for i in range(6):
        login=alice.post("/api/auth/login",json={
          "email":"sessions@example.com","password":"StrongPassword2026!"
        })
        assert login.status_code==200,login.text
    uid=alice.get("/api/auth/state").json()["user"]["id"]
    with sqlite3.connect(data/"identity.sqlite3") as db:
        count=db.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?",(uid,)).fetchone()[0]
    assert count<=5
    assert alice.get("/api/me").status_code==200
