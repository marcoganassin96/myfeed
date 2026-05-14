import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import SubscriptionField, TopicField

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock) -> TestClient:
    from handlers.subscriptions import router
    from dependencies import get_pool, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


def test_list_returns_subscriptions():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "technology",
         SubscriptionField.SUBSCRIBED_AT: "2026-01-01T00:00:00+00:00"}
    ]
    resp = _make_client(pool).get("/subscriptions")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0][TopicField.NAME] == "technology"


def test_post_subscribe_returns_201():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "technology",
        SubscriptionField.SUBSCRIBED_AT: "2026-01-01T00:00:00+00:00",
    }
    resp = _make_client(pool).post(
        "/subscriptions",
        json={SubscriptionField.TOPIC_ID: "t-1"},
    )
    assert resp.status_code == 201
    pool.fetchrow.assert_called_once()


def test_post_subscribe_returns_422_when_topic_id_missing():
    pool = AsyncMock()
    resp = _make_client(pool).post("/subscriptions", json={})
    assert resp.status_code == 422


def test_delete_returns_204():
    pool = AsyncMock()
    resp = _make_client(pool).delete("/subscriptions/t-1")
    assert resp.status_code == 204
    pool.execute.assert_called_once()


def test_list_returns_401_without_auth():
    from handlers.subscriptions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/subscriptions")
    assert resp.status_code == 401
