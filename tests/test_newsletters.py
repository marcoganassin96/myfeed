import json
import pytest
from fields import LambdaEvent, LambdaResponse, NewsletterField, EventField, ContextLinkField


@pytest.fixture
def list_event(api_event):
    return {**api_event, LambdaEvent.RESOURCE: "/newsletters", LambdaEvent.PATH: "/newsletters"}


@pytest.fixture
def get_event(api_event):
    return {
        **api_event,
        LambdaEvent.RESOURCE: "/newsletters/{newsletter_id}",
        LambdaEvent.PATH: "/newsletters/nl-uuid-001",
        LambdaEvent.PATH_PARAMETERS: {NewsletterField.ID: "nl-uuid-001"},
    }


def test_list_returns_cached_data(mock_cache, list_event):
    mock_get, _ = mock_cache
    mock_get.return_value = [{NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech Daily"}]

    from handlers.newsletters import handler
    resp = handler(list_event, {})

    assert resp[LambdaResponse.STATUS_CODE] == 200
    assert json.loads(resp[LambdaResponse.BODY]) == [{NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech Daily"}]


def test_list_queries_db_on_cache_miss(mock_db, mock_cache, list_event):
    mock_get, mock_set = mock_cache
    mock_get.return_value = None
    mock_db.fetchall.return_value = [
        {
            NewsletterField.ID: "nl-1", NewsletterField.TOPIC_ID: "t-1",
            NewsletterField.DATE: "2026-04-24", NewsletterField.TITLE: "Tech Daily",
        }
    ]

    from handlers.newsletters import handler
    resp = handler(list_event, {})

    assert resp[LambdaResponse.STATUS_CODE] == 200
    mock_db.execute.assert_called_once()
    mock_set.assert_called_once()


def test_get_by_id_returns_cached(mock_cache, get_event):
    mock_get, _ = mock_cache
    mock_get.return_value = {NewsletterField.ID: "nl-uuid-001", NewsletterField.TITLE: "Tech", NewsletterField.EVENTS: []}

    from handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp[LambdaResponse.STATUS_CODE] == 200
    assert json.loads(resp[LambdaResponse.BODY])[NewsletterField.ID] == "nl-uuid-001"


def test_get_by_id_returns_404_when_not_found(mock_db, mock_cache, get_event):
    mock_cache[0].return_value = None
    mock_db.fetchall.return_value = []

    from handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp[LambdaResponse.STATUS_CODE] == 404


def test_get_by_id_assembles_response_from_rows(mock_db, mock_cache, get_event):
    mock_cache[0].return_value = None
    mock_db.fetchall.side_effect = [
        [
            {
                NewsletterField.ID: "nl-uuid-001", NewsletterField.DATE: "2026-04-24",
                NewsletterField.TITLE: "Tech Daily", NewsletterField.NARRATIVE: "Today in tech...",
                EventField.POSITION: 1, EventField.ID: "ev-001",
                EventField.HEADLINE: "GPT-5.8 Released", EventField.SUMMARY: "OpenAI released...",
                EventField.EVENT_DATE: "2026-04-24", EventField.THREAD_ID: "th-001",
                EventField.THREAD_NAME: "GPT releases", EventField.PREVIOUS_EVENT_ID: None,
            }
        ],
        [
            {
                ContextLinkField.REASON: "Background on OpenAI", ContextLinkField.POSITION: 1,
                ContextLinkField.NEWSLETTER_ID: "nl-old", ContextLinkField.DATE: "2026-04-02",
                ContextLinkField.TITLE: "Tech Apr 2",
            },
        ],
    ]

    from handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp[LambdaResponse.STATUS_CODE] == 200
    body = json.loads(resp[LambdaResponse.BODY])
    assert body[NewsletterField.TITLE] == "Tech Daily"
    assert len(body[NewsletterField.EVENTS]) == 1
    assert body[NewsletterField.EVENTS][0][EventField.HEADLINE] == "GPT-5.8 Released"
    assert len(body[NewsletterField.CONTEXT_LINKS]) == 1
    mock_cache[1].assert_called_once()
