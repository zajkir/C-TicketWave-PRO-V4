"""Ceyrl Studio regression tests: existing account data and session security."""
from test_v5 import app_clients, signup
import ceyrl_features


def test_studio_assets_are_loaded_without_replacing_the_existing_workspace(app_clients):
    _, client, _, _ = app_clients
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "<title>Ceyrl — Your ticket workspace</title>" in html
    assert '/static/studio.css?v=studio-1' in html
    assert '/static/studio.js?v=studio-2' in html
    assert '/static/studio-refined.css?v=studio-2' in html
    assert '/static/x.js?v=studio-2' in html
    assert 'id="page-content"' in html
    assert 'Ceyrl Pro' not in html
    assert client.get("/static/studio.css").status_code == 200
    assert client.get("/static/studio.js").status_code == 200
    assert client.get("/static/studio-refined.css").status_code == 200


def test_session_management_is_private_and_requires_csrf(app_clients):
    _, alice, other_device, _ = app_clients
    assert alice.get("/api/me/sessions").status_code == 401
    a_csrf = signup(alice, "studio@example.com", "Studio User")
    second_login = other_device.post(
        "/api/auth/login",
        json={"email": "studio@example.com", "password": "StrongPassword2026!"},
    )
    assert second_login.status_code == 200, second_login.text

    own = alice.get("/api/me/sessions")
    assert own.status_code == 200, own.text
    body = own.json()
    assert body["active"] == 2
    assert body["other"] == 1
    assert body["current_expires_at"]
    assert "token_hash" not in str(body)
    assert "csrf" not in str(body)
    assert alice.post("/api/me/sessions/revoke-others").status_code == 403

    revoked = alice.post(
        "/api/me/sessions/revoke-others",
        headers={"x-csrf-token": a_csrf},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json() == {"ok": True, "revoked": 1}
    assert alice.get("/api/me/sessions").json()["active"] == 1
    assert other_device.get("/api/me").status_code == 401
    assert alice.get("/api/me").status_code == 200


def test_studio_radar_uses_actual_provider_media_and_safe_urls():
    source = {
        "id": "event2027", "name": "Real band", "url": "https://www.ticketmaster.com/event/abc123",
        "dates": {"start": {"dateTime": "2027-06-20T19:00:00Z", "localDate": "2027-06-20"}},
        "images": [
            {"ratio": "16_9", "url": "https://evil.example/tracker.png"},
            {"ratio": "16_9", "url": "https://s1.ticketm.net/dam/a/approved.jpg"},
        ],
    }
    safe = ceyrl_features.normalize_tm(source)
    assert safe["url"] == source["url"]
    assert safe["image_url"] == "https://s1.ticketm.net/dam/a/approved.jpg"
    unsafe = ceyrl_features.normalize_tm({
        **source, "url": "https://www.ticketmaster.com.evil.example/steal",
        "images": [{"ratio": "16_9", "url": "javascript:alert(1)"}],
    })
    assert unsafe["url"] == ""
    assert unsafe["image_url"] == ""
    assert ceyrl_features.safe_tm_url("https://www.ticketmaster.co.uk/event/123")
    assert not ceyrl_features.safe_tm_url("https://ticketmaster.com@evil.example/event/123")
    assert not ceyrl_features.safe_tm_url("https://evil.example/image.jpg", image=True)


def test_studio_client_wires_real_search_and_does_not_claim_fake_availability(app_clients):
    _, client, _, _ = app_clients
    script = client.get("/static/studio.js").text
    assert "xRadarSearch = async function studioRadarSearch" in script
    assert "api('/x/radar/search?q='" in script
    assert "resetPrivateRadarState" in script
    assert "retry-radar" in script
    assert "Date not confirmed" in script
    assert "studio-event-cover-photo" in script
    css = client.get("/static/studio-refined.css").text
    assert "prefers-reduced-motion:reduce" in css
    assert "max-width:570px" in css
