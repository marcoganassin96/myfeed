import json
from unittest.mock import AsyncMock, MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import DeepDiveField

_USER_ID = "test-user-sub"
_TEST_CHUNKS = ["chunk one", "chunk two"]


def _mock_resp(status: int, data=None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data or {}
    return r


def _make_client(mock_mdg: AsyncMock, chunks=None, interval=0.0) -> TestClient:
    from handlers.deep_dive import router, get_deep_dive_chunks, get_chunk_interval
    from dependencies import get_mdg_client, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    if chunks is not None:
        app.dependency_overrides[get_deep_dive_chunks] = lambda: chunks
    app.dependency_overrides[get_chunk_interval] = lambda: interval
    return TestClient(app)


# --- Cache HIT ---

def test_cache_hit_streams_cached_chunks():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, {"chunks": _TEST_CHUNKS})
    resp = _make_client(mdg, chunks=["ignored"]).post("/deep-dive/ev-001")
    assert resp.status_code == 200
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    data_chunks = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert data_chunks == _TEST_CHUNKS


def test_cache_hit_does_not_call_mdg_post():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, {"chunks": _TEST_CHUNKS})
    _make_client(mdg).post("/deep-dive/ev-001")
    mdg.post.assert_not_called()


# --- Cache MISS ---

def test_cache_miss_streams_fresh_chunks():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(404)
    mdg.post.return_value = _mock_resp(201)
    resp = _make_client(mdg, chunks=_TEST_CHUNKS).post("/deep-dive/ev-001")
    assert resp.status_code == 200
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    data_chunks = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert data_chunks == _TEST_CHUNKS


def test_cache_miss_posts_chunks_to_mdg():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(404)
    mdg.post.return_value = _mock_resp(201)
    _make_client(mdg, chunks=_TEST_CHUNKS).post("/deep-dive/ev-001")
    mdg.post.assert_called_once()
    _, kwargs = mdg.post.call_args
    assert kwargs["json"]["chunks"] == _TEST_CHUNKS
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


# --- MDG unavailable ---

def test_mdg_unavailable_streams_fresh_chunks_without_persisting():
    mdg = AsyncMock()
    mdg.get.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg, chunks=_TEST_CHUNKS).post("/deep-dive/ev-001")
    assert resp.status_code == 200
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    data_chunks = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert data_chunks == _TEST_CHUNKS
    mdg.post.assert_not_called()


# --- SSE format ---

def test_returns_200_with_sse_content_type():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(404)
    mdg.post.return_value = _mock_resp(201)
    resp = _make_client(mdg, chunks=_TEST_CHUNKS).post("/deep-dive/ev-001")
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_final_event_has_done_true():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(404)
    mdg.post.return_value = _mock_resp(201)
    resp = _make_client(mdg, chunks=_TEST_CHUNKS).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    last = json.loads(lines[-1][len("data: "):])
    assert last[DeepDiveField.DONE] is True
    assert last[DeepDiveField.CHUNK] == ""


def test_returns_401_without_auth():
    from handlers.deep_dive import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/deep-dive/ev-001")
    assert resp.status_code == 401
