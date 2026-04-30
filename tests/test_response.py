import json
from response import ok, created, no_content, bad_request, not_found, server_error
from fields import LambdaResponse, HttpHeader, ContentType


def test_ok_returns_200_with_json_body():
    resp = ok({"id": "123"})
    assert resp[LambdaResponse.STATUS_CODE] == 200
    assert json.loads(resp[LambdaResponse.BODY]) == {"id": "123"}
    assert resp[LambdaResponse.HEADERS][HttpHeader.CONTENT_TYPE] == ContentType.JSON


def test_created_returns_201():
    assert created({"id": "abc"})[LambdaResponse.STATUS_CODE] == 201


def test_no_content_returns_204_empty_body():
    resp = no_content()
    assert resp[LambdaResponse.STATUS_CODE] == 204
    assert resp[LambdaResponse.BODY] == ""


def test_bad_request_returns_400_with_message():
    resp = bad_request("topic_id is required")
    assert resp[LambdaResponse.STATUS_CODE] == 400
    assert json.loads(resp[LambdaResponse.BODY]) == {"error": "topic_id is required"}


def test_not_found_returns_404():
    resp = not_found("Newsletter not found")
    assert resp[LambdaResponse.STATUS_CODE] == 404
    assert json.loads(resp[LambdaResponse.BODY])["error"] == "Newsletter not found"


def test_server_error_returns_500():
    resp = server_error()
    assert resp[LambdaResponse.STATUS_CODE] == 500
    assert "error" in json.loads(resp[LambdaResponse.BODY])
