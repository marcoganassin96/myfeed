import json
from src import db
from src.response import ok, created, no_content, bad_request
from src.fields import SubscriptionField, TopicField, LambdaEvent, LambdaResponse, HttpMethod

_LIST_SQL = """
    SELECT s.topic_id, t.name, s.subscribed_at
    FROM subscriptions s JOIN topics t ON t.topic_id = s.topic_id
    WHERE s.user_id = %s ORDER BY s.subscribed_at DESC
"""
_INSERT_SQL = """
    INSERT INTO subscriptions (user_id, topic_id) VALUES (%s, %s)
    ON CONFLICT (user_id, topic_id) DO NOTHING
    RETURNING topic_id,
        (SELECT name FROM topics WHERE topic_id = %s) AS name,
        subscribed_at
"""
_DELETE_SQL = "DELETE FROM subscriptions WHERE user_id = %s AND topic_id = %s"


def handler(event, context):
    method, resource = event[LambdaEvent.HTTP_METHOD], event.get(LambdaEvent.RESOURCE, "")
    if method == HttpMethod.GET:
        return _list(event)
    if method == HttpMethod.POST:
        return _subscribe(event)
    if method == HttpMethod.DELETE and "{topic_id}" in resource:
        return _unsubscribe(event)
    return {LambdaResponse.STATUS_CODE: 405, LambdaResponse.BODY: json.dumps({"error": "Method not allowed"})}


def _uid(event):
    return event[LambdaEvent.REQUEST_CONTEXT][LambdaEvent.AUTHORIZER][LambdaEvent.CLAIMS][LambdaEvent.SUB]


def _list(event):
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_LIST_SQL, (_uid(event),))
        rows = cur.fetchall()
    return ok([
        {
            **dict(r),
            SubscriptionField.TOPIC_ID: str(dict(r)[SubscriptionField.TOPIC_ID]),
            SubscriptionField.SUBSCRIBED_AT: str(dict(r)[SubscriptionField.SUBSCRIBED_AT]),
        }
        for r in rows
    ])


def _subscribe(event):
    body = json.loads(event.get(LambdaEvent.BODY) or "{}")
    topic_id = body.get(SubscriptionField.TOPIC_ID)
    if not topic_id:
        return bad_request("topic_id is required")
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_INSERT_SQL, (_uid(event), topic_id, topic_id))
        row = dict(cur.fetchone() or {
            SubscriptionField.TOPIC_ID: topic_id,
            TopicField.NAME: None,
            SubscriptionField.SUBSCRIBED_AT: None,
        })
        conn.commit()
    return created({
        **row,
        SubscriptionField.TOPIC_ID: str(row[SubscriptionField.TOPIC_ID]),
        SubscriptionField.SUBSCRIBED_AT: str(row.get(SubscriptionField.SUBSCRIBED_AT, "")),
    })


def _unsubscribe(event):
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_DELETE_SQL, (_uid(event), event[LambdaEvent.PATH_PARAMETERS][SubscriptionField.TOPIC_ID]))
        conn.commit()
    return no_content()
