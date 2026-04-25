import json
import pytest
from src.fields import LambdaEvent, LambdaResponse, HttpMethod, SubscriptionField, TopicField


@pytest.fixture
def get_event(api_event):
    return {**api_event, LambdaEvent.HTTP_METHOD: HttpMethod.GET, LambdaEvent.RESOURCE: "/subscriptions"}


@pytest.fixture
def post_event(api_event):
    return {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/subscriptions",
        LambdaEvent.BODY: json.dumps({SubscriptionField.TOPIC_ID: "topic-uuid-001"}),
    }


@pytest.fixture
def delete_event(api_event):
    return {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.DELETE,
        LambdaEvent.RESOURCE: "/subscriptions/{topic_id}",
        LambdaEvent.PATH_PARAMETERS: {SubscriptionField.TOPIC_ID: "topic-uuid-001"},
    }


def test_list_returns_user_topics(mock_db, get_event):
    mock_db.fetchall.return_value = [
        {SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "technology", SubscriptionField.SUBSCRIBED_AT: "2026-01-01T00:00:00+00:00"}
    ]
    from src.handlers.subscriptions import handler
    resp = handler(get_event, {})
    assert resp[LambdaResponse.STATUS_CODE] == 200
    assert json.loads(resp[LambdaResponse.BODY])[0][TopicField.NAME] == "technology"


def test_post_returns_201(mock_db, post_event):
    mock_db.fetchone.return_value = {
        SubscriptionField.TOPIC_ID: "topic-uuid-001", TopicField.NAME: "technology",
        SubscriptionField.SUBSCRIBED_AT: "2026-04-24T00:00:00+00:00",
    }
    from src.handlers.subscriptions import handler
    resp = handler(post_event, {})
    assert resp[LambdaResponse.STATUS_CODE] == 201
    mock_db.execute.assert_called_once()


def test_post_returns_400_when_topic_id_missing(api_event):
    event = {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/subscriptions",
        LambdaEvent.BODY: "{}",
    }
    from src.handlers.subscriptions import handler
    assert handler(event, {})[LambdaResponse.STATUS_CODE] == 400


def test_delete_returns_204(mock_db, delete_event):
    from src.handlers.subscriptions import handler
    resp = handler(delete_event, {})
    assert resp[LambdaResponse.STATUS_CODE] == 204
    mock_db.execute.assert_called_once()
