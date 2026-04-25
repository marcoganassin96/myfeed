import json
from src.fields import LambdaResponse, HttpHeader, ContentType

_JSON = {HttpHeader.CONTENT_TYPE: ContentType.JSON}


def ok(body):
    return {LambdaResponse.STATUS_CODE: 200, LambdaResponse.HEADERS: _JSON, LambdaResponse.BODY: json.dumps(body, default=str)}


def created(body):
    return {LambdaResponse.STATUS_CODE: 201, LambdaResponse.HEADERS: _JSON, LambdaResponse.BODY: json.dumps(body, default=str)}


def no_content():
    return {LambdaResponse.STATUS_CODE: 204, LambdaResponse.HEADERS: {}, LambdaResponse.BODY: ""}


def bad_request(message: str):
    return {LambdaResponse.STATUS_CODE: 400, LambdaResponse.HEADERS: _JSON, LambdaResponse.BODY: json.dumps({"error": message})}


def not_found(message: str = "Not found"):
    return {LambdaResponse.STATUS_CODE: 404, LambdaResponse.HEADERS: _JSON, LambdaResponse.BODY: json.dumps({"error": message})}


def server_error(message: str = "Internal server error"):
    return {LambdaResponse.STATUS_CODE: 500, LambdaResponse.HEADERS: _JSON, LambdaResponse.BODY: json.dumps({"error": message})}
