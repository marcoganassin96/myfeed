import json
import pytest
from fields import LambdaEvent, LambdaResponse, HttpMethod, InteractionField, InteractionType


@pytest.fixture
def post_event(api_event):
    return {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/interactions",
        LambdaEvent.BODY: json.dumps({InteractionField.EVENT_ID: "ev-uuid-001", InteractionField.TYPE: InteractionType.CLICK}),
    }


def test_post_records_interaction_and_returns_201(mock_db, post_event):
    mock_db.fetchone.return_value = {InteractionField.ID: "ix-1", InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00"}
    from handlers.interactions import handler
    resp = handler(post_event, {})
    assert resp[LambdaResponse.STATUS_CODE] == 201
    mock_db.execute.assert_called_once()


def test_post_returns_400_when_event_id_missing(api_event):
    event = {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/interactions",
        LambdaEvent.BODY: json.dumps({InteractionField.TYPE: InteractionType.CLICK}),
    }
    from handlers.interactions import handler
    assert handler(event, {})[LambdaResponse.STATUS_CODE] == 400


def test_post_returns_400_when_type_invalid(api_event):
    event = {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/interactions",
        LambdaEvent.BODY: json.dumps({InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: "unknown"}),
    }
    from handlers.interactions import handler
    assert handler(event, {})[LambdaResponse.STATUS_CODE] == 400


def test_post_accepts_all_valid_types(mock_db, api_event):
    mock_db.fetchone.return_value = {InteractionField.ID: "ix-1", InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00"}
    from handlers.interactions import handler
    for t in InteractionType:
        event = {
            **api_event,
            LambdaEvent.HTTP_METHOD: HttpMethod.POST,
            LambdaEvent.RESOURCE: "/interactions",
            LambdaEvent.BODY: json.dumps({InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: t}),
        }
        assert handler(event, {})[LambdaResponse.STATUS_CODE] == 201, f"Expected 201 for type={t}"
