"""Keyless ConcertHub integration: real-source contract, isolation and safe dates.

No live ConcertHub requests are made in CI; those require a production smoke test.
"""
from datetime import datetime, timezone, timedelta

import ceyrl_concerthub
import ceyrl_radar
from test_v5 import app_clients, signup


def next_year_date():
    return (datetime.now(timezone.utc) + timedelta(days=300)).date().isoformat()


def public_concert(date_value=None):
    return {
        "artist": "Example Band",
        "title": "Example Band Live",
        "slug": "example-band-warszawa-2027",
        "date": date_value or next_year_date(),
        "venue": "Example Arena",
        "city": "Warszawa",
        "url": "https://evil.example/dont-trust-me",
    }


def test_concerthub_strict_validation_and_unknown_time():
    row=ceyrl_concerthub.normalize_concerthub(public_concert())
    assert row is not None
    assert row["provider"]=="ConcertHub"
    assert row["url"]=="https://concerthub.pl/en/event/example-band-warszawa-2027"
    assert row["country"]=="PL"
    assert row["starts_at"]==""  # Date is real, exact start time is unknown.
    assert row["local_date"]==next_year_date()
    assert ceyrl_radar._valid_provider_url(row["url"])
    assert not ceyrl_radar._valid_provider_url(
        "https://concerthub.pl.evil.example/en/event/example-band-warszawa-2027")
    assert not ceyrl_radar._valid_provider_url(
        "https://concerthub.pl/en/event/../../admin")
    assert ceyrl_concerthub.normalize_concerthub(
        {**public_concert(),"slug":"../../evil"}) is None
    assert ceyrl_concerthub.normalize_concerthub(
        {**public_concert(),"date":"2008-09-01"}) is None


def test_concerthub_keyless_search_and_explicit_import_is_private(app_clients,monkeypatch):
    _,alice,bob,_=app_clients
    csrf_a=signup(alice,"ch-alice@example.com","ConcertHub Alice")
    csrf_b=signup(bob,"ch-bob@example.com","ConcertHub Bob")
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.delenv("TICKETMASTER_API_KEY",raising=False)
    monkeypatch.setattr(ceyrl_radar,"search_public",lambda q,c:[])
    monkeypatch.setattr(ceyrl_concerthub,"search_concerthub",
                        lambda q,c:[ceyrl_concerthub.normalize_concerthub(public_concert())])
    status=alice.get("/api/x/radar/status")
    assert status.status_code==200
    assert status.json()["key_required"] is False
    assert status.json()["keyless_search_enabled"] is True
    assert "ConcertHub (Poland)" in status.json()["keyless_sources"]
    result=alice.get("/api/x/radar/search?q=Example%20Band&country=PL&kind=music")
    assert result.status_code==200,result.text
    data=result.json()
    assert len(data["events"])==1
    assert "ConcertHub (Poland)" in data["sources_checked"]
    assert data["events"][0]["starts_at"]==""
    assert bob.post("/api/x/radar/import/ch:example-band-warszawa-2027",
                    headers={"x-csrf-token":csrf_b}).status_code==404
    # The provider supplied only a day, not a UTC hour. Do not guess midnight.
    attempt=alice.post("/api/x/radar/import/ch:example-band-warszawa-2027",
                       headers={"x-csrf-token":csrf_a})
    assert attempt.status_code==422
    assert alice.get("/api/events").json()==[]


def test_concerthub_timed_event_import_without_any_user_key(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    csrf=signup(alice,"ch-timed@example.com","Concert Timed")
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.delenv("TICKETMASTER_API_KEY",raising=False)
    monkeypatch.setattr(ceyrl_radar,"search_public",lambda q,c:[])
    date_text=next_year_date()+"T20:30:00+01:00"
    monkeypatch.setattr(ceyrl_concerthub,"search_concerthub",lambda q,c:[
        ceyrl_concerthub.normalize_concerthub(public_concert(date_text))
    ])
    result=alice.get("/api/x/radar/search?q=Example%20Band&country=PL")
    assert result.status_code==200,result.text
    event=result.json()["events"][0]
    assert event["starts_at"]!=""
    added=alice.post("/api/x/radar/import/"+event["id"],headers={"x-csrf-token":csrf})
    assert added.status_code==200,added.text
    assert alice.get("/api/events").json()[0]["title"]=="Example Band Live"


def test_country_filter_never_leaks_poland_events_into_slovakia(app_clients,monkeypatch):
    _,alice,_,_=app_clients
    signup(alice,"ch-country@example.com","Concert Country")
    monkeypatch.delenv("CTW_TICKETMASTER_API_KEY",raising=False)
    monkeypatch.delenv("TICKETMASTER_API_KEY",raising=False)
    monkeypatch.setattr(ceyrl_radar,"search_public",lambda q,c:[])
    monkeypatch.setattr(ceyrl_concerthub,"search_concerthub",lambda q,c:
        (_ for _ in ()).throw(AssertionError("Polish source should not run for SK")))
    r=alice.get("/api/x/radar/search?q=Example%20Band&country=SK&kind=music")
    assert r.status_code==200
    assert r.json()["events"]==[]
    assert "ConcertHub (Poland)" not in r.json()["sources_checked"]


def test_keyless_interface_has_direct_external_search_links(app_clients):
    _,client,_,_=app_clients
    js=client.get("/static/aurora.js").text
    assert "Rozšírené vyhľadávanie nenastavené" not in js
    assert "Kľúč na serveri nastavený" not in js
    assert "concerthub.pl" in js
    links=client.get("/static/studio.js").text
    assert "Ticketmaster search" in links
    assert "Songkick search" in links
    assert "Bandsintown search" in links
    assert "ConcertHub Poland" in links
