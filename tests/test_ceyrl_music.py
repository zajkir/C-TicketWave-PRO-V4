"""Ceyrl Radar mainstream artists: Noah Kahan, Nickelback, BTS and more.

All providers are mocked. CI never claims to verify live 2026-27 concert dates.
"""
from datetime import datetime, timezone
from urllib.parse import quote
import ceyrl_music
import ceyrl_gigora
import pytest

@pytest.fixture(autouse=True)
def mock_extra_gigora(monkeypatch):
    # These legacy StungEvents tests must stay independent of live Gigora.
    monkeypatch.setattr(ceyrl_gigora,"search",lambda *args,**kwargs:
        ([],{"checked":[],"errors":[]}))
import ceyrl_radar
from test_v5 import app_clients, signup


SAMPLE_EVENTS = [
    {"slug":"noah-kahan-boston-2027-04-10-abc12345",
     "title":"Noah Kahan – Boston",
     "start_utc":"2027-04-11T00:00:00Z","venue_name":"Example Arena",
     "city":"Boston","country":"US","category":"concerts"},
    {"slug":"nickelback-london-2027-06-22-aaa22334",
     "title":"Nickelback Live in London",
     "start_utc":"2027-06-22T18:00:00Z","venue_name":"Test London Hall",
     "city":"London","country":"United Kingdom","category":"concerts"},
    {"slug":"bts-seoul-2027-08-12-bts25111",
     "title":"BTS World Tour – Seoul",
     "start_utc":"2027-08-12T11:00:00Z","venue_name":"Sample Stadium",
     "city":"Seoul","country":"South Korea","category":"concerts"},
]


def fake_provider(url,params,headers=None):
    assert url==ceyrl_music.STUNG_SEARCH
    query=params.get("q","").casefold()
    return {"ok":True,"events":[item for item in SAMPLE_EVENTS
        if query.split()[0] in item["title"].casefold()]}


def test_major_artists_return_normalized_concerts_without_user_keys(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    a=signup(alice,"music-major-a@example.com","Major A")
    b=signup(bob,"music-major-b@example.com","Major B")
    monkeypatch.delenv("CTW_TICKETS_DEV_API_KEY",raising=False)
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.setattr(ceyrl_music,"_get_json",fake_provider)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    ceyrl_music._CACHE.clear()

    for artist in ("Noah Kahan","Nickelback","BTS"):
        result=alice.get("/api/x/radar/search?q="+quote(artist)+"&kind=music")
        assert result.status_code==200,result.text
        data=result.json()
        assert len(data["events"])==1
        assert data["events"][0]["provider"]=="StungEvents"
        assert data["events"][0]["category"]=="Concert"
        assert data["events"][0]["name"].casefold().startswith(artist.casefold())
        assert data["events"][0]["url"].startswith("https://stungevents.com/event/")
        assert data["sources_checked"]==["StungEvents"]
        assert data["provider_warnings"]==[]

    # A private search result must not be importable from another user's space.
    searched=alice.get("/api/x/radar/search?q=BTS&kind=music")
    eid=searched.json()["events"][0]["id"]
    assert eid.startswith("se:")
    denied=bob.post("/api/x/radar/import/"+eid,headers={"x-csrf-token":b})
    assert denied.status_code==404
    saved=alice.post("/api/x/radar/import/"+eid,headers={"x-csrf-token":a})
    assert saved.status_code==200,saved.text
    assert alice.get("/api/events").json()[0]["title"]=="BTS World Tour – Seoul"
    assert bob.get("/api/events").json()==[]


def test_concert_country_filter_and_absent_artist_are_honest(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"music-filter@example.com","Music Filter")
    monkeypatch.setattr(ceyrl_music,"_get_json",fake_provider)
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    monkeypatch.delenv("CTW_TICKETS_DEV_API_KEY",raising=False)
    ceyrl_music._CACHE.clear()
    england=alice.get("/api/x/radar/search?q=Nickelback&kind=music&country=GB")
    assert england.status_code==200
    assert len(england.json()["events"])==1
    slovakia=alice.get("/api/x/radar/search?q=Nickelback&kind=music&country=SK")
    assert slovakia.status_code==200
    assert slovakia.json()["events"]==[]
    not_found=alice.get("/api/x/radar/search?q=Rare%20Artist%20XYZ&kind=music")
    assert not_found.status_code==200
    assert not_found.json()["events"]==[]
    assert "StungEvents" in not_found.json()["sources_checked"]
    assert "Not all artists" in not_found.json()["coverage_note"]


def test_tickets_dev_server_only_catalog_normalization_and_url_validation(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"music-dev@example.com","Catalog test")
    monkeypatch.setenv("CTW_TICKETS_DEV_API_KEY","server-secret-for-tests")
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    ceyrl_music._CACHE.clear()
    calls=[]
    def two_providers(url,params,headers=None):
        calls.append((url,params,headers))
        if url==ceyrl_music.STUNG_SEARCH:
            return {"ok":True,"events":[]}
        if url==ceyrl_music.TICKETS_DEV_EVENTS:
            assert headers["x-api-key"]=="server-secret-for-tests"
            return {"events":[{
                "id":"01SOMEEVENTCATALOG2027",
                "name":"BTS Concert in Paris",
                "eventDateUtc":"2027-04-10T19:00:00Z",
                "eventDateLocal":"2027-04-10T21:00:00+02:00",
                "venue":{"name":"Paris Example","city":"Paris","country":"FR"},
                "sources":[
                    {"marketplace":"stubhub","url":"https://www.stubhub.com/unsafe-or-not-listed"},
                    {"marketplace":"ticketmaster",
                     "url":"https://www.ticketmaster.com/bts-paris-tickets/event/1AB2027"}]
            }]}
        raise AssertionError(url)
    monkeypatch.setattr(ceyrl_music,"_get_json",two_providers)
    response=alice.get("/api/x/radar/search?q=BTS&country=FR&kind=music")
    assert response.status_code==200,response.text
    data=response.json()
    assert "Tickets.dev" in data["sources_checked"]
    assert len(data["events"])==1
    event=data["events"][0]
    assert event["id"]=="td:01SOMEEVENTCATALOG2027"
    assert event["url"]=="https://www.ticketmaster.com/bts-paris-tickets/event/1AB2027"
    assert event["local_date"]=="2027-04-10"
    assert ceyrl_music.tickets_dev_event({
        "id":"01SOMEEVENTCATALOG2027","name":"Malicious link",
        "eventDateUtc":"2027-04-10T19:00:00Z",
        "venue":{"country":"FR"},
        "sources":[{"url":"https://ticketmaster.com.attacker.example/fake"}]
    }) is None
    assert ceyrl_radar._valid_provider_url("javascript:alert(1)") is False
    assert ceyrl_radar._valid_provider_url("https://stungevents.com.attacker.example/event/stolen") is False


def test_public_provider_outage_is_warning_and_not_invented_results(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"music-outage@example.com","Outage")
    ceyrl_music._CACHE.clear()
    monkeypatch.delenv("CTW_TICKETS_DEV_API_KEY",raising=False)
    monkeypatch.setattr(ceyrl_music,"_get_json",lambda *args,**kwargs:
        (_ for _ in ()).throw(ValueError("outage")))
    monkeypatch.setattr(ceyrl_radar,"request_public",lambda q,c:[])
    response=alice.get("/api/x/radar/search?q=Noah%20Kahan&kind=music")
    assert response.status_code==200,response.text
    data=response.json()
    assert data["events"]==[]
    assert data["sources_checked"]==["Ticket Fairy"]
    assert "StungEvents event catalog unavailable" in data["provider_warnings"]


def test_stung_malformed_date_and_urls_cannot_be_imported():
    data={**SAMPLE_EVENTS[0]}
    assert ceyrl_music.stung_event({**data,"start_utc":"not a date"}) is None
    assert ceyrl_music.stung_event({**data,"slug":"../../admin"}) is None
    assert ceyrl_music.stung_event({**data,"country":"US"},"SK") is None
    assert ceyrl_music.stung_event({**data,"category":"football"},"","music") is None
    assert ceyrl_music.stung_event(data)
    item=ceyrl_music.stung_event(data)
    assert ceyrl_radar._valid_provider_url(item["url"])
