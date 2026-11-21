"""Regression tests for invite-only Google OAuth integration.

No real Google credentials or network access are needed for these checks.
"""
from urllib.parse import parse_qs, urlparse

from test_app import clients, bootstrap


def test_google_is_off_until_hosting_secrets_are_configured(clients):
    _, admin, _, _, _ = clients
    state = admin.get('/api/auth/state')
    assert state.status_code == 200
    assert state.json()['google_enabled'] is False
    assert admin.get('/api/auth/google/start', follow_redirects=False).status_code == 503


def test_google_requires_existing_workspace_and_invites(clients, monkeypatch):
    module, admin, member, _, _ = clients
    monkeypatch.setenv('CTW_GOOGLE_CLIENT_ID', 'test-app.apps.googleusercontent.com')
    monkeypatch.setenv('CTW_GOOGLE_CLIENT_SECRET', 'local-test-secret-only')
    monkeypatch.setenv('CTW_PUBLIC_BASE_URL', 'https://tickets.example.test')

    # A Google account cannot create the first administrator.
    assert member.get('/api/auth/google/start', follow_redirects=False).status_code == 403

    csrf = bootstrap(admin)
    assert admin.get('/api/auth/state').json()['google_enabled'] is True

    # A random non-invited Google account cannot initiate registration.
    assert member.get('/api/auth/google/start?mode=invite&invite=fake', follow_redirects=False).status_code == 403

    invited = admin.post(
        '/api/team/invites',
        headers={'X-CSRF-Token': csrf},
        json={'email': 'teammate@gmail.com', 'role': 'viewer'}
    )
    assert invited.status_code == 200
    invitation_token = invited.json()['token']

    response = member.get('/api/auth/google/start?mode=invite&invite=' + invitation_token,
                          follow_redirects=False)
    assert response.status_code == 302
    parsed = urlparse(response.headers['location'])
    assert parsed.hostname == 'accounts.google.com'
    query = parse_qs(parsed.query)
    assert query['client_id'] == ['test-app.apps.googleusercontent.com']
    assert query['redirect_uri'] == ['https://tickets.example.test/api/auth/google/callback']
    assert query['code_challenge_method'] == ['S256']
    assert 'openid' in query['scope'][0]
    assert query['nonce'][0]
    assert query['state'][0]
    assert response.cookies['ctw_google_oauth'] == query['state'][0]

    # A forged callback cannot create an account.
    invalid = member.get('/api/auth/google/callback?state=invalid&code=bad',
                         follow_redirects=False)
    assert invalid.status_code == 303
    assert 'google_error=state' in invalid.headers['location']
    assert len(module.fetch('SELECT id FROM users')) == 1
