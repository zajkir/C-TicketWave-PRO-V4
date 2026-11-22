"""Ceyrl Aurora screenshot-led theme regression checks.

This style layer must keep the existing backend and action dispatch intact.
"""
from test_v5 import app_clients, signup


def test_aurora_assets_load_after_studio_without_changing_brand(app_clients):
    _, client, _, _ = app_clients
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert '<title>Ceyrl — Your ticket workspace</title>' in html
    assert 'Ceyrl Pro' not in html
    assert '/static/aurora.css?v=aurora-4' in html
    assert '/static/aurora.js?v=aurora-4' in html
    assert html.index('studio-dashboard.css') < html.index('aurora.css')
    assert html.index('studio-dashboard.js') < html.index('aurora.js')
    assert client.get('/static/aurora.css').status_code == 200
    assert client.get('/static/aurora.js').status_code == 200
    assert client.get('/static/concert-aurora.svg').status_code == 200


def test_all_modules_share_theme_and_accessible_motion_fallback(app_clients):
    _, client, _, _ = app_clients
    css = client.get('/static/aurora.css').text
    for selector in (
        '.sidebar', '.topbar', '.page-content', '.auth-layout',
        '.studio3-hero-primary', '.studio-account-header',
        '.data-table', '.modal-window', '.studio-settings-panel',
        '.ceyrl-radar', '.ceyrl-event-grid',
    ):
        assert selector in css
    assert 'prefers-reduced-motion:reduce' in css
    assert 'ceyrl-aurora-entry' in css
    assert 'url(\'/static/concert-aurora.svg\')' in css


def test_radar_displays_only_real_data_and_uses_existing_handlers(app_clients):
    _, client, _, _ = app_clients
    js = client.get('/static/aurora.js').text
    assert "api('/x/radar/status')" in js
    assert "api('/x/radar/watches')" in js
    assert 'renderXRadar = async function renderAuroraRadar' in js
    assert 'xRadarResultsHtml = cardsHtml' in js
    assert 'id="x-radar-form"' in js
    assert 'id="x-radar-query"' in js
    assert 'id="x-radar-country"' in js
    assert 'id="x-radar-kind"' in js
    for action in ['data-x-import=', 'data-x-artist=', 'data-x-action="radar-refresh"', 'data-x-action="radar-follow"', 'data-x-remove-watch=']:
        assert action in js
    assert 'Stav neznámy' in js
    assert 'Rozšírené vyhľadávanie nenastavené' in js
    assert 'Nezobrazujeme vymyslené koncerty ani ceny.' in js
    assert 'data-aurora-view' in js
    assert 'ceyrl-date-from' in js
    assert 'ceyrl-date-to' in js


def test_radar_private_account_requirement_is_unchanged(app_clients):
    _, alice, bob, _ = app_clients
    assert alice.get('/api/x/radar/status').status_code == 401
    signup(alice, 'aurora-alice@example.com', 'Aurora Alice')
    signup(bob, 'aurora-bob@example.com', 'Aurora Bob')
    assert alice.get('/api/x/radar/status').status_code == 200
    assert bob.get('/api/x/radar/status').status_code == 200
    assert alice.get('/api/x/radar/watches').json()['watches'] == []
    assert bob.get('/api/x/radar/watches').json()['watches'] == []
