from unittest.mock import AsyncMock, MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import SubscriptionField, TopicField

_USER_ID = "test-user-sub"


def _mock_resp(status: int, data) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    return r


def _make_client(mock_mdg: AsyncMock) -> TestClient:
    from handlers.subscriptions import router
    from dependencies import get_mdg_client, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


# --- GET /subscriptions ---

def test_list_returns_200_and_body():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, [{SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "tech"}])
    resp = _make_client(mdg).get("/subscriptions")
    assert resp.status_code == 200
    assert resp.json()[0][TopicField.NAME] == "tech"


def test_list_passes_user_id_header():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(200, [])
    _make_client(mdg).get("/subscriptions")
    _, kwargs = mdg.get.call_args
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


def test_list_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.get.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).get("/subscriptions")
    assert resp.status_code == 503


def test_list_returns_502_on_mdg_5xx():
    mdg = AsyncMock()
    mdg.get.return_value = _mock_resp(500, {})
    resp = _make_client(mdg).get("/subscriptions")
    assert resp.status_code == 502


def test_list_returns_401_without_auth():
    from handlers.subscriptions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/subscriptions")
    assert resp.status_code == 401


# --- POST /subscriptions ---

def test_post_subscribe_returns_201():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(201, {SubscriptionField.TOPIC_ID: "t-1"})
    resp = _make_client(mdg).post("/subscriptions", json={SubscriptionField.TOPIC_ID: "t-1"})
    assert resp.status_code == 201
    mdg.post.assert_called_once()


def test_post_subscribe_forwards_topic_id_in_body():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(201, {})
    _make_client(mdg).post("/subscriptions", json={SubscriptionField.TOPIC_ID: "t-99"})
    _, kwargs = mdg.post.call_args
    assert kwargs["json"][SubscriptionField.TOPIC_ID] == "t-99"


def test_post_subscribe_returns_422_when_topic_id_missing():
    mdg = AsyncMock()
    resp = _make_client(mdg).post("/subscriptions", json={})
    assert resp.status_code == 422
    mdg.post.assert_not_called()


def test_post_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.post.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).post("/subscriptions", json={SubscriptionField.TOPIC_ID: "t-1"})
    assert resp.status_code == 503


# --- DELETE /subscriptions/{topic_id} ---

def test_delete_returns_204():
    mdg = AsyncMock()
    mdg.delete.return_value = _mock_resp(204, None)
    resp = _make_client(mdg).delete("/subscriptions/t-1")
    assert resp.status_code == 204
    mdg.delete.assert_called_once()


def test_delete_passes_user_id_header():
    mdg = AsyncMock()
    mdg.delete.return_value = _mock_resp(204, None)
    _make_client(mdg).delete("/subscriptions/t-1")
    _, kwargs = mdg.delete.call_args
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


def test_delete_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.delete.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).delete("/subscriptions/t-1")
    assert resp.status_code == 503


def test_delete_returns_502_on_mdg_5xx():
    mdg = AsyncMock()
    mdg.delete.return_value = _mock_resp(500, {})
    resp = _make_client(mdg).delete("/subscriptions/t-1")
    assert resp.status_code == 502
