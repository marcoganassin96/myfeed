import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_pool, mock_redis):
    with patch("db_async.create_pool", return_value=mock_pool), \
         patch("cache_async.create_redis", return_value=mock_redis):
        from main import app
        with TestClient(app) as c:
            yield c


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_body(client):
    resp = client.get("/health")
    assert resp.json() == {"status": "ok"}


def test_health_does_not_require_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_newsletters_route_registered(client, mock_pool, mock_redis):
    from dependencies import get_pool, get_redis, get_user_id
    from main import app
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    mock_redis.get.return_value = "[]"
    resp = client.get("/newsletters")
    assert resp.status_code == 200
    app.dependency_overrides.clear()


def test_interactions_route_registered(client):
    from dependencies import get_pool, get_user_id
    from main import app
    pool = AsyncMock()
    pool.fetchrow.return_value = {"interaction_id": "ix-1", "created_at": "2026-01-01"}
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    resp = client.post("/interactions", json={"event_id": "ev-1", "type": "view"})
    assert resp.status_code == 201
    app.dependency_overrides.clear()
