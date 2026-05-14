import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import NewsletterField, EventField, ContextLinkField, HttpHeader, CacheStatus

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock, redis: AsyncMock) -> TestClient:
    from handlers.newsletters import router
    from dependencies import get_pool, get_redis, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


# --- GET /newsletters ---

def test_list_returns_200_on_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps([{NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech"}])
    pool = AsyncMock()
    resp = _make_client(pool, redis).get("/newsletters")
    assert resp.status_code == 200
    assert resp.json()[0][NewsletterField.ID] == "nl-1"
    assert resp.headers.get("x-lambda-cache") == CacheStatus.HIT


def test_list_does_not_query_pool_on_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps([])
    pool = AsyncMock()
    _make_client(pool, redis).get("/newsletters")
    pool.fetch.assert_not_called()


def test_list_queries_pool_on_cache_miss():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.return_value = [
        {NewsletterField.ID: "nl-1", NewsletterField.TOPIC_ID: "t-1",
         NewsletterField.DATE: "2026-04-24", NewsletterField.TITLE: "Tech Daily"}
    ]
    resp = _make_client(pool, redis).get("/newsletters")
    assert resp.status_code == 200
    assert resp.headers.get("x-lambda-cache") == CacheStatus.MISS
    pool.fetch.assert_called_once()
    redis.set.assert_called_once()


def test_list_returns_401_without_auth():
    from handlers.newsletters import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/newsletters")
    assert resp.status_code == 401


# --- GET /newsletters/{newsletter_id} ---

def test_get_by_id_returns_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps({NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech", NewsletterField.EVENTS: []})
    pool = AsyncMock()
    resp = _make_client(pool, redis).get("/newsletters/nl-1")
    assert resp.status_code == 200
    assert resp.json()[NewsletterField.ID] == "nl-1"
    assert resp.headers.get("x-lambda-cache") == CacheStatus.HIT
    pool.fetch.assert_not_called()


def test_get_by_id_returns_404_when_not_found():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.return_value = []
    resp = _make_client(pool, redis).get("/newsletters/missing")
    assert resp.status_code == 404


def test_get_by_id_assembles_response_from_rows():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.side_effect = [
        # _GET_SQL rows
        [{
            NewsletterField.ID: "nl-1", NewsletterField.DATE: "2026-04-24",
            NewsletterField.TITLE: "Tech Daily", NewsletterField.NARRATIVE: "Today...",
            EventField.POSITION: 1, EventField.ID: "ev-1",
            EventField.HEADLINE: "Headline", EventField.SUMMARY: "Summary",
            EventField.EVENT_DATE: "2026-04-24", EventField.THREAD_ID: "th-1",
            EventField.THREAD_NAME: "Thread A", EventField.PREVIOUS_EVENT_ID: None,
        }],
        # _LINKS_SQL rows
        [{
            ContextLinkField.REASON: "Background", ContextLinkField.POSITION: 1,
            ContextLinkField.NEWSLETTER_ID: "nl-old", ContextLinkField.DATE: "2026-04-01",
            ContextLinkField.TITLE: "Old Tech",
        }],
    ]
    resp = _make_client(pool, redis).get("/newsletters/nl-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body[NewsletterField.TITLE] == "Tech Daily"
    assert len(body[NewsletterField.EVENTS]) == 1
    assert body[NewsletterField.EVENTS][0][EventField.HEADLINE] == "Headline"
    assert len(body[NewsletterField.CONTEXT_LINKS]) == 1
    assert resp.headers.get("x-lambda-cache") == CacheStatus.MISS
    redis.set.assert_called_once()
