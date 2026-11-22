"""The Studio dashboard is structurally replaced, not merely recolored."""
from test_v5 import app_clients, signup

def test_studio_dashboard_assets_loaded_and_brand_is_ceyrl(app_clients):
    _, client, _, _ = app_clients
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert '/static/studio-dashboard.css?v=studio-3' in html
    assert '/static/studio-dashboard.js?v=studio-3' in html
    assert html.index('studio-dashboard.js') > html.index('studio.js?v=studio-2')
    assert "Ceyrl Pro" not in html
    assert client.get("/static/studio-dashboard.css").status_code == 200
    assert client.get("/static/studio-dashboard.js").status_code == 200

def test_studio_dashboard_uses_live_private_data_and_existing_actions(app_clients):
    _, client, _, _ = app_clients
    javascript = client.get("/static/studio-dashboard.js").text
    assert "renderOverview = async function renderStudio3Overview" in javascript
    assert "api('/dashboard')" in javascript
    assert "api('/events')" in javascript
    for action in ["new-event", "new-ticket", "new-sale"]:
        assert "'" + action + "'" in javascript
    for page in ["radar","analytics","events","sales"]:
        assert "'" + page + "'" in javascript
    assert "Your next event starts here" in javascript
    assert "No upcoming events" in javascript
    assert "data-studio3-retry" in javascript

def test_studio_dashboard_keeps_account_data_private(app_clients):
    _, alice, bob, _ = app_clients
    assert alice.get("/api/dashboard").status_code == 401
    assert bob.get("/api/events").status_code == 401
    signup(alice, "studio-dashboard-alice@example.com", "Studio Alice")
    signup(bob, "studio-dashboard-bob@example.com", "Studio Bob")
    events = alice.get("/api/events")
    assert events.status_code == 200
    assert events.json() == []
    assert bob.get("/api/events").json() == []
    assert alice.get("/api/dashboard").status_code == 200
    assert bob.get("/api/dashboard").status_code == 200
