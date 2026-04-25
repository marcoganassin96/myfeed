import json
from src.fields import DeepDiveField, LambdaEvent, LambdaResponse, HttpMethod, HttpHeader, ContentType

_MOCK_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]


def handler(event, context):
    if event[LambdaEvent.HTTP_METHOD] != HttpMethod.POST:
        return {
            LambdaResponse.STATUS_CODE: 405,
            LambdaResponse.HEADERS: {HttpHeader.CONTENT_TYPE: ContentType.JSON},
            LambdaResponse.BODY: json.dumps({"error": "Method not allowed"}),
        }

    return {
        LambdaResponse.STATUS_CODE: 200,
        LambdaResponse.HEADERS: {
            HttpHeader.CONTENT_TYPE: ContentType.SSE,
            HttpHeader.CACHE_CONTROL: "no-cache",
            HttpHeader.X_ACCEL_BUFFERING: "no",
        },
        LambdaResponse.BODY: _build_sse(_MOCK_CHUNKS),
    }


def _build_sse(chunks: list[str]) -> str:
    lines = []
    for text in chunks:
        lines.append(f"data: {json.dumps({DeepDiveField.CHUNK: text, DeepDiveField.DONE: False})}")
        lines.append("")
    lines.append(f"data: {json.dumps({DeepDiveField.CHUNK: '', DeepDiveField.DONE: True})}")
    lines.append("")
    return "\n".join(lines)
