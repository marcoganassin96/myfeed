import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import DeepDiveField

_USER_ID = "test-user-sub"
_TEST_CHUNKS = ["chunk one", "chunk two"]


def _make_client(chunks=None, interval=0.0) -> TestClient:
    from handlers.deep_dive import router, get_deep_dive_chunks, get_chunk_interval
    from dependencies import get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    if chunks is not None:
        app.dependency_overrides[get_deep_dive_chunks] = lambda: chunks
    app.dependency_overrides[get_chunk_interval] = lambda: interval
    return TestClient(app)


def test_deep_dive_returns_200_with_sse_content_type():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_deep_dive_streams_chunks_in_order():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    chunks_received = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert chunks_received == _TEST_CHUNKS


def test_deep_dive_final_event_has_done_true():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    last = json.loads(lines[-1][len("data: "):])
    assert last[DeepDiveField.DONE] is True
    assert last[DeepDiveField.CHUNK] == ""


def test_deep_dive_uses_default_chunks_when_not_overridden():
    from handlers.deep_dive import router, get_chunk_interval, _DEFAULT_CHUNKS
    from dependencies import get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    app.dependency_overrides[get_chunk_interval] = lambda: 0.0
    resp = TestClient(app).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    data_chunks = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert data_chunks == _DEFAULT_CHUNKS


def test_deep_dive_returns_401_without_auth():
    from handlers.deep_dive import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/deep-dive/ev-001")
    assert resp.status_code == 401
