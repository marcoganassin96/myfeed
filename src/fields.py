from enum import StrEnum


class TopicField(StrEnum):
    ID = "topic_id"
    NAME = "name"
    DESCRIPTION = "description"


class ThreadField(StrEnum):
    ID = "thread_id"
    TOPIC_ID = "topic_id"
    NAME = "name"
    CREATED_AT = "created_at"


class EventField(StrEnum):
    ID = "event_id"
    HEADLINE = "headline"
    SUMMARY = "summary"
    DATE = "date"
    EVENT_DATE = "event_date"
    SOURCE_URL = "source_url"
    THREAD_ID = "thread_id"
    THREAD_NAME = "thread_name"
    PREVIOUS_EVENT_ID = "previous_event_id"
    POSITION = "position"


class NewsletterField(StrEnum):
    ID = "newsletter_id"
    TOPIC_ID = "topic_id"
    DATE = "date"
    TITLE = "title"
    NARRATIVE = "narrative"
    EVENTS = "events"
    CONTEXT_LINKS = "context_links"
    POSITION = "position"


class ContextLinkField(StrEnum):
    REASON = "reason"
    POSITION = "position"
    NEWSLETTER_ID = "newsletter_id"
    DATE = "date"
    TITLE = "title"


class SubscriptionField(StrEnum):
    USER_ID = "user_id"
    TOPIC_ID = "topic_id"
    SUBSCRIBED_AT = "subscribed_at"


class InteractionField(StrEnum):
    ID = "interaction_id"
    USER_ID = "user_id"
    EVENT_ID = "event_id"
    TYPE = "type"
    CREATED_AT = "created_at"


class InteractionType(StrEnum):
    VIEW = "view"
    CLICK = "click"
    DEEP_DIVE = "deep_dive"


class DeepDiveField(StrEnum):
    CHUNK = "chunk"
    DONE = "done"


class CachePrefix(StrEnum):
    NEWSLETTER = "newsletter:"
    USER_LATEST = "newsletters:user:"


class EnvVar(StrEnum):
    DB_HOST = "DB_HOST"
    DB_NAME = "DB_NAME"
    DB_USER = "DB_USER"
    DB_PASSWORD = "DB_PASSWORD"
    DB_PORT = "DB_PORT"
    REDIS_HOST = "REDIS_HOST"
    REDIS_PORT = "REDIS_PORT"
    REDIS_SSL = "REDIS_SSL"
    COGNITO_USER_POOL_ID = "COGNITO_USER_POOL_ID"
    AWS_REGION = "AWS_REGION"
    DEEP_DIVE_INTERVAL = "DEEP_DIVE_INTERVAL"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class HttpHeader(StrEnum):
    CONTENT_TYPE = "Content-Type"
    CACHE_CONTROL = "Cache-Control"
    AUTHORIZATION = "Authorization"
    X_ACCEL_BUFFERING = "X-Accel-Buffering"
    X_CACHE = "X-Lambda-Cache"


class CacheStatus(StrEnum):
    HIT = "HIT"
    MISS = "MISS"


class ContentType(StrEnum):
    JSON = "application/json"
    SSE = "text/event-stream"


class LambdaEvent(StrEnum):
    HTTP_METHOD = "httpMethod"
    RESOURCE = "resource"
    PATH = "path"
    PATH_PARAMETERS = "pathParameters"
    QUERY_STRING_PARAMETERS = "queryStringParameters"
    HEADERS = "headers"
    REQUEST_CONTEXT = "requestContext"
    BODY = "body"
    AUTHORIZER = "authorizer"
    CLAIMS = "claims"
    SUB = "sub"


class HttpResource(StrEnum):
    HEALTH = "/health"


class LambdaResponse(StrEnum):
    STATUS_CODE = "statusCode"
    HEADERS = "headers"
    BODY = "body"
