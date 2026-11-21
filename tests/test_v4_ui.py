"""V4 layout regressions - no frontend navigation to removed tools."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v4_frontend_assets_and_removed_navigation():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    css = (ROOT / 'static/v4.css').read_text(encoding='utf-8')
    nav = js.split('const groups=[', 1)[1].split('];', 1)[0]
    for old in ['recaps', 'discovery', 'watchlist', 'integrations']:
        assert f"['{old}'" not in nav
        assert f"case'{old}'" not in js
    assert 'recap-overlay' not in html
    assert 'v4.css' in html
    assert 'global-search' in html
    assert 'ticketRow(t)' in js
    assert 'renderEventBreakdown' in js
    assert 'auth-info' in html
    assert '--blue:#5c95f8' in css


def test_v4_backend_keeps_data_compatible_but_disables_unwanted_auto_sync():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert "version='4.0.0'" in app
    assert "CTW_ENABLE_LEGACY_WATCHLIST" in app
    assert 'app.mount(\'/static\'' in app
