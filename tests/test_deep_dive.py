import json
import pytest
from fields import LambdaEvent, LambdaResponse, HttpMethod, HttpHeader, ContentType, DeepDiveField, EventField


@pytest.fixture
def deep_dive_event(api_event):
    return {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.POST,
        LambdaEvent.RESOURCE: "/deep-dive/{event_id}",
        LambdaEvent.PATH: "/deep-dive/ev-uuid-001",
        LambdaEvent.PATH_PARAMETERS: {EventField.ID: "ev-uuid-001"},
    }


def test_returns_200_with_sse_content_type(deep_dive_event):
    from handlers.deep_dive import handler
    resp = handler(deep_dive_event, {})
    assert resp[LambdaResponse.STATUS_CODE] == 200
    assert resp[LambdaResponse.HEADERS][HttpHeader.CONTENT_TYPE] == ContentType.SSE


def test_body_contains_sse_data_lines(deep_dive_event):
    from handlers.deep_dive import handler
    lines = [l for l in handler(deep_dive_event, {})[LambdaResponse.BODY].split("\n") if l.startswith("data:")]
    assert len(lines) >= 2


def test_last_chunk_has_done_true(deep_dive_event):
    from handlers.deep_dive import handler
    data_lines = [l[6:] for l in handler(deep_dive_event, {})[LambdaResponse.BODY].split("\n") if l.startswith("data:")]
    assert json.loads(data_lines[-1])[DeepDiveField.DONE] is True


def test_non_last_chunks_have_done_false_and_content(deep_dive_event):
    from handlers.deep_dive import handler
    data_lines = [l[6:] for l in handler(deep_dive_event, {})[LambdaResponse.BODY].split("\n") if l.startswith("data:")]
    for line in data_lines[:-1]:
        chunk = json.loads(line)
        assert chunk[DeepDiveField.DONE] is False
        assert len(chunk[DeepDiveField.CHUNK]) > 0


def test_returns_405_for_get(api_event):
    event = {
        **api_event,
        LambdaEvent.HTTP_METHOD: HttpMethod.GET,
        LambdaEvent.RESOURCE: "/deep-dive/{event_id}",
        LambdaEvent.PATH_PARAMETERS: {EventField.ID: "ev-001"},
    }
    from handlers.deep_dive import handler
    assert handler(event, {})[LambdaResponse.STATUS_CODE] == 405
