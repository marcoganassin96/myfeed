from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    from dependencies import get_mdg_client, get_user_id
    from main import app
    mock_mdg = AsyncMock()
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    return TestClient(app)


def test_health_returns_200():
    with patch("settings.load", return_value={"mdg": {"url": "http://mdg:9000", "connect_timeout": 2.0, "read_timeout": 10.0, "write_timeout": 5.0, "pool_timeout": 2.0}}):
        resp = _make_client().get("/health")
    assert resp.status_code == 200


def test_health_body():
    with patch("settings.load", return_value={"mdg": {"url": "http://mdg:9000", "connect_timeout": 2.0, "read_timeout": 10.0, "write_timeout": 5.0, "pool_timeout": 2.0}}):
        resp = _make_client().get("/health")
    assert resp.json() == {"status": "ok"}


def test_health_does_not_require_auth():
    with patch("settings.load", return_value={"mdg": {"url": "http://mdg:9000", "connect_timeout": 2.0, "read_timeout": 10.0, "write_timeout": 5.0, "pool_timeout": 2.0}}):
        resp = _make_client().get("/health")
    assert resp.status_code == 200


def test_newsletters_route_registered():
    from dependencies import get_mdg_client, get_user_id
    from main import app
    mock_mdg = AsyncMock()
    mock_mdg.get.return_value = type("R", (), {"status_code": 200, "json": lambda self: []})()
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    resp = TestClient(app).get("/newsletters")
    assert resp.status_code == 200
    app.dependency_overrides.clear()


def test_interactions_route_registered():
    from dependencies import get_mdg_client, get_user_id
    from main import app
    mock_mdg = AsyncMock()
    mock_mdg.post.return_value = type("R", (), {"status_code": 201, "json": lambda self: {"interaction_id": "ix-1", "created_at": "2026-01-01"}})()
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    resp = TestClient(app).post("/interactions", json={"event_id": "ev-1", "type": "view"})
    assert resp.status_code == 201
    app.dependency_overrides.clear()
