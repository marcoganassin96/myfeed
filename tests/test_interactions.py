import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import InteractionField, InteractionType

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock) -> TestClient:
    from handlers.interactions import router
    from dependencies import get_pool, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


def test_post_records_interaction_and_returns_201():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        InteractionField.ID: "ix-1",
        InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00",
    }
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 201
    pool.fetchrow.assert_called_once()


def test_post_returns_422_when_event_id_missing():
    pool = AsyncMock()
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 422


def test_post_returns_422_when_type_invalid():
    pool = AsyncMock()
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: "not_a_type"},
    )
    assert resp.status_code == 422


def test_post_accepts_all_valid_types():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        InteractionField.ID: "ix-1",
        InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00",
    }
    for t in InteractionType:
        resp = _make_client(pool).post(
            "/interactions",
            json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: t},
        )
        assert resp.status_code == 201, f"Expected 201 for type={t}"


def test_post_returns_401_without_auth():
    from handlers.interactions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/interactions", json={})
    assert resp.status_code == 401
