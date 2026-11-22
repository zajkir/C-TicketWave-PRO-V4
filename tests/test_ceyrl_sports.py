"""Event Radar sports fixes: no-key football discovery, import isolation and provider diagnostics."""
from datetime import datetime, timezone
import ceyrl_sports
import ceyrl_radar
import ceyrl_features
from test_v5 import app_clients, signup

ESPN_FIXTURE = {
    "id":"401777899","name":"Spain vs France",
    "date":"2027-03-25T19:45:00Z",
    "competitions":[{"venue":{
        "fullName":"National Stadium",
        "address":{"city":"Madrid","country":"Spain"}}}]
}
SPORTSDB_FIXTURE = {
    "idEvent":"1876543","strEvent":"England vs Norway",
    "strTimestamp":"2027-03-25T20:45:00+01:00",
    "dateEvent":"2027-03-25","strVenue":"Wembley Stadium",
    "strCountry":"England","strCity":"London",
    "idLeague":"4490","strLeague":"UEFA Nations League"
}


def _fake_fixtures(url,params):
    if "site.api.espn.com" in url:
        assert "uefa.nations" in url
        return {"events":[ESPN_FIXTURE]}
    if url.endswith("eventsnextleague.php"):
        assert params["id"]=="4490"
        return {"events":[SPORTSDB_FIXTURE]}
    if url.endswith("searchevents.php"):
        return {"events":None}
    raise AssertionError("Unexpected or untrusted provider endpoint: "+url)


def test_nations_league_keyless_search_finds_sports_events_and_safe_import(app_clients,monkeypatch):
    _,alice,bob,_ = app_clients
    a=signup(alice,"sports-radar-a@example.com","Sports A")
    b=signup(bob,"sports-radar-b@example.com","Sports B")
    ceyrl_sports.CACHE.clear()
    monkeypatch.setattr(ceyrl_sports,"_fetch_json",_fake_fixtures)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    query="/api/x/radar/search?q=Nations%20league&country=&kind=all"
    response=alice.get(query)
    assert response.status_code==200,response.text
    data=response.json()
    assert data["events"]
    assert {"ESPN schedules","TheSportsDB"}.issubset(set(data["sources_checked"]))
    assert all(x["category"]=="Sports" for x in data["events"])
    assert any(x["provider"]=="ESPN" for x in data["events"])
    assert any(x["provider"]=="TheSportsDB" for x in data["events"])
    one=next(x for x in data["events"] if x["provider"]=="TheSportsDB")
    assert one["name"]=="England vs Norway"
    assert one["id"]=="sp:ts:1876543"
    assert one["local_date"]=="2027-03-25"
    assert one["url"]=="https://www.thesportsdb.com/event/1876543"
    other=next(x for x in data["events"] if x["provider"]=="ESPN")
    assert other["id"]=="sp:es:401777899"
    assert other["starts_at"]=="2027-03-25T19:45:00+00:00"
    assert bob.post("/api/x/radar/import/sp:ts:1876543",
        headers={"x-csrf-token":b}).status_code==404
    imported=alice.post("/api/x/radar/import/sp:ts:1876543",
        headers={"x-csrf-token":a})
    assert imported.status_code==200,imported.text
    assert alice.get("/api/events").json()[0]["title"]=="England vs Norway"
    assert not bob.get("/api/events").json()


def test_sport_filter_search_uses_public_feeds_without_ticketfairy(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"sports-filter@example.com","Sports filter")
    ceyrl_sports.CACHE.clear()
    monkeypatch.setattr(ceyrl_sports,"_fetch_json",_fake_fixtures)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:
        (_ for _ in ()).throw(AssertionError("No music provider for sports-only search")))
    result=alice.get("/api/x/radar/search?q=Nations%20league&kind=sports")
    assert result.status_code==200,result.text
    assert len(result.json()["events"])==2
    assert "Ticket Fairy" not in result.json()["sources_checked"]


def test_provider_degradation_visible_instead_of_faking_no_matches(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"sports-outage@example.com","Outage test")
    ceyrl_sports.CACHE.clear()
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    def broken_provider(url,params):
        raise ValueError("test outage")
    monkeypatch.setattr(ceyrl_sports,"_fetch_json",broken_provider)
    response=alice.get("/api/x/radar/search?q=Nations%20league&kind=all")
    assert response.status_code==200,response.text
    data=response.json()
    assert data["events"]==[]
    assert "Ticket Fairy" in data["sources_checked"]
    assert data["provider_warnings"]
    assert any("ESPN" in x for x in data["provider_warnings"])
    assert any("TheSportsDB" in x for x in data["provider_warnings"])


def test_sports_unknown_time_not_importable_and_source_urls_are_verified(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    token=signup(alice,"sports-safe@example.com","Sports safe")
    ceyrl_sports.CACHE.clear()
    incomplete={**SPORTSDB_FIXTURE,"idEvent":"1876888",
                "strTimestamp":"","dateEvent":"2027-04-25"}
    def no_time(url,params):
        if "espn" in url:return {"events":[]}
        if url.endswith("eventsnextleague.php"):return {"events":[incomplete]}
        return {"events":None}
    monkeypatch.setattr(ceyrl_sports,"_fetch_json",no_time)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    searched=alice.get("/api/x/radar/search?q=Nations%20league")
    assert searched.status_code==200,searched.text
    event=next(x for x in searched.json()["events"] if x["id"]=="sp:ts:1876888")
    assert event["starts_at"]==""
    not_imported=alice.post("/api/x/radar/import/sp:ts:1876888",
                             headers={"x-csrf-token":token})
    assert not_imported.status_code==422
    assert not alice.get("/api/events").json()
    assert ceyrl_radar._valid_provider_url("https://www.thesportsdb.com.evil.com/event/1876888") is False
    assert ceyrl_radar._valid_provider_url("javascript:alert(1)") is False
    assert ceyrl_radar._valid_provider_url("https://www.thesportsdb.com/event/1876888")
    assert ceyrl_radar._valid_provider_url("https://www.espn.com/soccer/match/_/gameId/401777899")
