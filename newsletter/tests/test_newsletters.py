from unittest.mock import AsyncMock, MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import NewsletterField

_USER_ID = "test-user-sub"
_NL_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _mock_resp(status: int, data) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    return r


def _make_client(mock_mdg: AsyncMock) -> TestClient:
    from handlers.newsletters import router
    from dependencies import get_mdg_client, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


# --- GET /newsletters ---

def test_list_returns_200_and_body_from_mdg():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, [{NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech"}])
    resp = _make_client(mdg).get("/newsletters")
    assert resp.status_code == 200
    assert resp.json()[0][NewsletterField.ID] == "nl-1"
    mdg.get.assert_called_once()


def test_list_passes_user_id_header():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, [])
    _make_client(mdg).get("/newsletters")
    _, kwargs = mdg.get.call_args
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


def test_list_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.get.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).get("/newsletters")
    assert resp.status_code == 503


def test_list_returns_503_on_timeout():
    mdg = AsyncMock()
    mdg.get.side_effect = httpx.TimeoutException("timeout")
    resp = _make_client(mdg).get("/newsletters")
    assert resp.status_code == 503


def test_list_returns_502_on_mdg_5xx():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(500, {"error": "internal"})
    resp = _make_client(mdg).get("/newsletters")
    assert resp.status_code == 502


def test_list_returns_401_without_auth():
    from handlers.newsletters import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/newsletters")
    assert resp.status_code == 401


# --- GET /newsletters/{newsletter_id} ---

def test_get_by_id_returns_200_and_body_from_mdg():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, {NewsletterField.ID: _NL_ID, NewsletterField.TITLE: "Tech"})
    resp = _make_client(mdg).get(f"/newsletters/{_NL_ID}")
    assert resp.status_code == 200
    assert resp.json()[NewsletterField.ID] == _NL_ID


def test_get_by_id_passes_user_id_header():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, {NewsletterField.ID: _NL_ID})
    _make_client(mdg).get(f"/newsletters/{_NL_ID}")
    _, kwargs = mdg.get.call_args
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


def test_get_by_id_returns_404_from_mdg():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(404, {"error": "not found"})
    resp = _make_client(mdg).get(f"/newsletters/{_NL_ID}")
    assert resp.status_code == 404


def test_get_by_id_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.get.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).get(f"/newsletters/{_NL_ID}")
    assert resp.status_code == 503


def test_get_by_id_returns_502_on_mdg_5xx():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(500, {"error": "internal"})
    resp = _make_client(mdg).get(f"/newsletters/{_NL_ID}")
    assert resp.status_code == 502


# --- client is None (lifespan not started) ---

def test_list_returns_503_when_mdg_client_none():
    resp = _make_client(None).get("/newsletters")
    assert resp.status_code == 503


def test_get_by_id_returns_503_when_mdg_client_none():
    resp = _make_client(None).get(f"/newsletters/{_NL_ID}")
    assert resp.status_code == 503
