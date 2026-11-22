"""Regression tests for public Gigora concerts and graceful StungEvents fallback.

All external lookups are mocked; no real tours are asserted or invented.
"""
from urllib.parse import quote

import ceyrl_gigora
import ceyrl_music
import ceyrl_radar
from test_v5 import app_clients, signup


CONCERTS=[
    {
      "title":"Noah Kahan Example Tour — Boston",
      "starts_at":"2027-08-19T23:00:00Z",
      "venue":{"name":"Sample Concert Hall","city":"Boston","country":"United States"},
      "headliner":"Noah Kahan",
      "gigora_url":"https://gigora.live/concerts/noah-kahan-boston-2027?utm_source=ai",
    },
    {
      "title":"Nickelback — London",
      "starts_at":"2027-09-21T19:00:00Z",
      "venue":{"name":"Sample O2","city":"London","country":"United Kingdom"},
      "headliner":"Nickelback",
      "gigora_url":"https://gigora.live/concerts/nickelback-london-2027?utm_source=ai",
    },
    {
      "title":"BTS — Seoul",
      "starts_at":"2027-10-12T11:00:00Z",
      "venue":{"name":"Sample Stadium","city":"Seoul","country":"South Korea"},
      "headliner":"BTS",
      "gigora_url":"https://gigora.live/concerts/bts-seoul-2027?utm_source=ai",
    }
]


def test_gigora_artist_search_requires_no_keys_and_import_stays_private(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    a=signup(alice,"gigora-a@example.com","Gigora A")
    b=signup(bob,"gigora-b@example.com","Gigora B")
    ceyrl_gigora._CACHED.clear()
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.delenv("CTW_TICKETS_DEV_API_KEY",raising=False)
    calls=[]
    def gigora(artist,country):
        calls.append((artist,country))
        return [e for e in CONCERTS if artist.casefold() in e["title"].casefold()]
    monkeypatch.setattr(ceyrl_gigora,"request_gigora",gigora)
    # On successful new source, the failing Stung backup must not be consulted.
    monkeypatch.setattr(ceyrl_music,"search",lambda *args:
       (_ for _ in ()).throw(AssertionError("No backup query when Gigora works")))
    monkeypatch.setattr(ceyrl_radar,"search_public",lambda *args:
       (_ for _ in ()).throw(AssertionError("No Ticket Fairy needed")))
    for name in ("Noah Kahan","Nickelback","BTS"):
        result=alice.get("/api/x/radar/search?q="+quote(name)+"&kind=music")
        assert result.status_code==200,result.text
        body=result.json()
        assert body["sources_checked"]==["Gigora"]
        assert body["provider_warnings"]==[]
        assert len(body["events"])==1
        show=body["events"][0]
        assert show["provider"]=="Gigora"
        assert show["id"].startswith("gi:")
        assert show["category"]=="Concert"
        assert name.casefold() in show["name"].casefold()
        assert show["url"].startswith("https://gigora.live/concerts/")
    assert len(calls)==3

    saved=alice.get("/api/x/radar/search?q=BTS&kind=music").json()["events"][0]
    denied=bob.post("/api/x/radar/import/"+saved["id"],
                    headers={"x-csrf-token":b})
    assert denied.status_code==404
    authorized=alice.post("/api/x/radar/import/"+saved["id"],
                          headers={"x-csrf-token":a})
    assert authorized.status_code==200,authorized.text
    assert alice.get("/api/events").json()[0]["title"]=="BTS — Seoul"
    assert bob.get("/api/events").json()==[]


def test_gigora_country_filter_and_cache(monkeypatch):
    ceyrl_gigora._CACHED.clear()
    calls=[]
    def provider(a,c):
        calls.append((a,c))
        return CONCERTS
    monkeypatch.setattr(ceyrl_gigora,"request_gigora",provider)
    uk,diag=ceyrl_gigora.search("Nickelback","GB","music")
    assert diag["checked"]==["Gigora"]
    assert [e["name"] for e in uk]==["Nickelback — London"]
    uk2,_=ceyrl_gigora.search("Nickelback","GB","music")
    assert uk2==uk and len(calls)==1
    sk,_=ceyrl_gigora.search("Nickelback","SK","music")
    assert sk==[]
    assert len(calls)==2


def test_gigora_failure_uses_available_backup_without_claiming_empty_tour(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"gigora-fallback@example.com","Fallback")
    ceyrl_gigora._CACHED.clear()
    monkeypatch.setattr(ceyrl_gigora,"request_gigora",lambda *args:
      (_ for _ in ()).throw(ValueError("provider down")))
    fallback=ceyrl_music.stung_event({
        "slug":"bts-2027-seoul-backup","title":"BTS — Seoul",
        "start_utc":"2027-10-12T11:00:00Z","country":"South Korea",
        "city":"Seoul","venue":"Sample Stadium","category":"concerts"
    })
    assert fallback is not None
    monkeypatch.setattr(ceyrl_music,"search",lambda *args:
        ([fallback],{"checked":["StungEvents"],"errors":[]}))
    monkeypatch.setattr(ceyrl_radar,"search_public",lambda *args:
        (_ for _ in ()).throw(AssertionError("Backup was successful")))
    res=alice.get("/api/x/radar/search?q=BTS&kind=music")
    assert res.status_code==200,res.text
    body=res.json()
    assert len(body["events"])==1
    assert body["events"][0]["name"]=="BTS — Seoul"
    assert body["provider_warnings"]==["Gigora concert feed unavailable"]
    assert "StungEvents" in body["sources_checked"]


def test_gigora_rejects_non_gigora_sources_and_unsafe_dates():
    item=CONCERTS[0]
    assert ceyrl_gigora.normalize(item,artist="Noah Kahan")
    assert ceyrl_gigora.normalize({**item,"gigora_url":"https://gigora.live.attacker.com/event/fake"}) is None
    assert ceyrl_gigora.normalize({**item,"gigora_url":"javascript:alert(1)"}) is None
    assert ceyrl_gigora.normalize({**item,"gigora_url":"https://gigora.live/api/secret"}) is None
    assert ceyrl_gigora.normalize({**item,"gigora_url":"https://gigora.live/concerts/foo?admin=true"}) is None
    assert ceyrl_gigora.normalize({**item,"starts_at":"invalid"}) is None
    assert ceyrl_gigora.normalize({**item,"title":""}) is None
    assert ceyrl_radar._valid_provider_url(item["gigora_url"])
    assert not ceyrl_radar._valid_provider_url("https://evil-gigora.live/concerts/fake")


def test_gigora_missing_timezone_cannot_be_imported(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    csrf=signup(alice,"gigora-unknown@example.com","Gigora unknown time")
    ceyrl_gigora._CACHED.clear()
    monkeypatch.setattr(ceyrl_gigora,"request_gigora",lambda *args:
        [{**CONCERTS[0],"starts_at":"2027-08-19T19:00:00"}])
    monkeypatch.setattr(ceyrl_music,"search",lambda *args:
        (_ for _ in ()).throw(AssertionError("No backup needed")))
    matches=alice.get("/api/x/radar/search?q=Noah%20Kahan&kind=music")
    assert matches.status_code==200,matches.text
    row=matches.json()["events"][0]
    assert row["starts_at"]==""
    refused=alice.post("/api/x/radar/import/"+row["id"],
                       headers={"x-csrf-token":csrf})
    assert refused.status_code==422
    assert alice.get("/api/events").json()==[]
