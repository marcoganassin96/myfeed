from unittest.mock import AsyncMock, MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import InteractionField, InteractionType

_USER_ID = "test-user-sub"


def _mock_resp(status: int, data) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    return r


def _make_client(mock_mdg: AsyncMock) -> TestClient:
    from handlers.interactions import router
    from dependencies import get_mdg_client, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_mdg_client] = lambda: mock_mdg
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


def test_post_returns_201_and_body():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(201, {InteractionField.ID: "ix-1"})
    resp = _make_client(mdg).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 201
    assert resp.json()[InteractionField.ID] == "ix-1"


def test_post_forwards_payload_to_mdg():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(201, {})
    _make_client(mdg).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.VIEW},
    )
    _, kwargs = mdg.post.call_args
    assert kwargs["json"][InteractionField.EVENT_ID] == "ev-001"
    assert kwargs["json"][InteractionField.TYPE] == InteractionType.VIEW
    assert kwargs["headers"]["X-User-Id"] == _USER_ID


def test_post_returns_422_when_event_id_missing():
    mdg = AsyncMock()
    resp = _make_client(mdg).post(
        "/interactions",
        json={InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 422
    mdg.post.assert_not_called()


def test_post_returns_422_when_type_invalid():
    mdg = AsyncMock()
    resp = _make_client(mdg).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: "not_a_type"},
    )
    assert resp.status_code == 422


def test_post_accepts_all_valid_types():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(201, {})
    for t in InteractionType:
        resp = _make_client(mdg).post(
            "/interactions",
            json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: t},
        )
        assert resp.status_code == 201, f"Expected 201 for type={t}"


def test_post_returns_503_on_connect_error():
    mdg = AsyncMock()
    mdg.post.side_effect = httpx.ConnectError("down")
    resp = _make_client(mdg).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.VIEW},
    )
    assert resp.status_code == 503


def test_post_returns_502_on_mdg_5xx():
    mdg = AsyncMock()
    mdg.post.return_value = _mock_resp(500, {})
    resp = _make_client(mdg).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.VIEW},
    )
    assert resp.status_code == 502


def test_post_returns_401_without_auth():
    from handlers.interactions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/interactions", json={})
    assert resp.status_code == 401
