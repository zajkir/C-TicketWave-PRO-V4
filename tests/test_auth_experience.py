"""Regression checks for the centered Ceyrl sign-in, Google login and recovery UI."""
from test_v5 import app_clients


def test_auth_layout_is_last_css_layer_and_all_auth_controls_exist(app_clients):
    _, client, _, _ = app_clients
    response=client.get("/")
    assert response.status_code==200
    html=response.text
    assert '<link rel="stylesheet" href="/static/auth-experience.css?v=auth-6">' in html
    assert html.index('experience.css?v=experience-5') < html.index('auth-experience.css?v=auth-6')
    assert '<div class="auth-mobile-brand"' in html
    assert 'Your Ceyrl workspace' in html
    assert 'Portfolio performance' not in html
    assert '+€2,480.00' not in html
    for element_id in [
        'auth-view','auth-main','auth-form','auth-email','auth-password','auth-submit',
        'auth-google','google-button','auth-switch','forgot-link','password-toggle',
        'auth-note','auth-errors','auth-name-row'
    ]:
        assert 'id="'+element_id+'"' in html or ('class="'+element_id+'"' in html)
    assert html.index('class="auth-footer"') > html.index('id="auth-form"')


def test_footer_flow_fix_and_responsive_auth_styles(app_clients):
    _, client, _, _ = app_clients
    layout=client.get('/static/auth-experience.css')
    ambient=client.get('/static/ambient.css')
    assert layout.status_code==200
    assert ambient.status_code==200
    css=layout.text
    assert '#auth-view .auth-main' in css
    assert 'flex-direction:column !important' in css or 'flex-direction:column!important' in css
    assert '#auth-view .auth-footer' in css
    assert 'position:relative!important' in css
    assert 'bottom:auto!important' in css
    assert '#auth-view .auth-card' in css
    assert '#auth-view .auth-aside' in css
    assert '@media(max-width:1020px)' in css
    assert '@media(max-width:560px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css
    assert '.auth-aside-inner, .auth-card, .auth-footer { position: relative;' not in ambient.text


def test_login_behavior_and_security_are_not_replaced_by_visual_redesign(app_clients):
    _, client, _, _ = app_clients
    code=client.get('/static/app.js').text
    for marker in [
        "async function authSubmit(", "function showAuth(mode)",
        "'/auth/login'", "'/auth/register'", "'/auth/forgot'",
        "app.csrf=response.csrf"
    ]:
        assert marker in code
    assert client.get("/api/me").status_code == 401
