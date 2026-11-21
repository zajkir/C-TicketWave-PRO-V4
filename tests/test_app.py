"""Safe, small regression fixtures for the C TicketWave V4 backend."""
import importlib.util
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv("CTW_DATA_DIR", str(tmp_path / "persist"))
    monkeypatch.setenv("CTW_SECURE_COOKIES", "0")
    monkeypatch.setenv("CTW_ALLOW_LOCAL_SETUP", "1")
    spec = importlib.util.spec_from_file_location(
        "ticketwave_test_" + secrets.token_hex(6),
        Path(__file__).resolve().parents[1] / "app.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with (
        TestClient(module.app, base_url="http://testserver") as admin,
        TestClient(module.app, base_url="http://testserver") as operator,
        TestClient(module.app, base_url="http://testserver") as viewer,
    ):
        yield module, admin, operator, viewer, tmp_path / "persist"


def bootstrap(admin):
    response = admin.post(
        "/api/auth/bootstrap",
        json={
            "email": "owner@example.test",
            "password": "LocalTestCredential2026!",
            "name": "Team Owner",
            "setup_code": "",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf"]


def write(client, path, data=None, csrf="", method="POST", **kwargs):
    return client.request(
        method,
        "/api" + path,
        headers={"X-CSRF-Token": csrf},
        json=data,
        **kwargs,
    )


def event_body(name="Example Concert"):
    return {
        "title": name,
        "starts_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "venue": "Sample Venue",
        "city": "Prague",
        "country": "Czechia",
        "category": "Concert",
    }


def test_health_and_authenticated_event_flow(clients):
    _, admin, _, viewer, _ = clients
    assert admin.get("/health").json()["status"] == "ok"
    assert viewer.get("/api/events").status_code == 401
    csrf = bootstrap(admin)
    assert admin.get("/api/events").status_code == 200
    event = write(admin, "/events", event_body(), csrf)
    assert event.status_code == 200, event.text
    assert len(admin.get("/api/events").json()) == 1
    assert write(admin, "/events", event_body(), "invalid-token").status_code == 403
