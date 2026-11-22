"""Contract tests for the reference-led Ceyrl experience.
The UI reads authenticated endpoints and preserves existing buttons/actions.
"""
from test_v5 import app_clients, signup


def test_experience_is_loaded_last_and_csp_allows_only_selected_photo_host(app_clients):
    _, client, _, _ = app_clients
    r=client.get('/')
    assert r.status_code==200
    html=r.text
    assert '/static/experience.css?v=experience-5' in html
    assert '/static/experience.js?v=experience-5' in html
    assert html.index('aurora.css') < html.index('experience.css')
    assert html.index('aurora.js') < html.index('experience.js')
    assert '<title>Ceyrl — Your ticket workspace</title>' in html
    assert 'Ceyrl Pro' not in html
    assert client.get('/static/experience.css').status_code==200
    assert client.get('/static/experience.js').status_code==200
    csp=r.headers['content-security-policy']
    assert 'https://images.unsplash.com' in csp
    assert "script-src 'self'" in csp
    assert "object-src 'none'" in csp


def test_experience_reuses_real_backends_and_adds_working_ui_controls(app_clients):
    _, client, _, _ = app_clients
    code=client.get('/static/experience.js').text
    assert "api('/events')" in code
    for name in ['renderEvents','renderTickets','renderSales','renderAnalytics','renderSettings','renderXRadar']:
        assert name in code
    for id in ['ceyrl-event-filter','ceyrl-event-state','ceyrl-ticket-card-grid',
               'ticket-filter','ticket-status','ceyrl-sales-filter',
               'ceyrl-settings-section-','data-ceyrl-horizon','ceyrl-profit-row']:
        assert id in code
    for action in ['new-event','edit-event','new-ticket','manage-pdf',
                   'sale-ticket','new-sale','export-sales']:
        assert action in code
    assert "data-page" in code
    assert "aria-current" in code
    assert 'dataset.ceyrlPage' in code
    assert 'ceyrl-calendar-level-' in code
    assert 'ceyrl-profit-level-' in code
    assert 'style="height:' not in code
    assert 'style="width:' not in code


def test_all_page_styles_reuse_existing_security_and_accessibility(app_clients):
    _, client, _, _ = app_clients
    css=client.get('/static/experience.css').text
    for term in ['.ceyrl-private-event-card','.ceyrl-ticket-card',
                 '.ceyrl-settings-layout','.ceyrl-profit-bars',
                 '.ceyrl-collection-toolbar','.ceyrl-panel-segments',
                 '.ceyrl-radar-hero','.studio3-hero-primary',
                 '.auth-aside','.topbar','.sidebar']:
        assert term in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert '[hidden]{display:none!important}' in css


def test_account_data_is_unchanged_and_still_private_between_users(app_clients):
    _, alice, bob, _ = app_clients
    assert alice.get('/api/events').status_code == 401
    assert bob.get('/api/tickets').status_code == 401
    signup(alice,'experience-one@example.com','One Account')
    signup(bob,'experience-two@example.com','Two Account')
    for client in [alice,bob]:
        assert client.get('/api/events').status_code == 200
        assert client.get('/api/tickets').status_code == 200
        assert client.get('/api/me').status_code == 200
        assert client.get('/api/me/sessions').status_code == 200
