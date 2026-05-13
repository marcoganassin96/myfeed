import json
import db
import cache
from response import ok, not_found
from fields import (
    NewsletterField, EventField, ContextLinkField, CachePrefix,
    LambdaEvent, LambdaResponse, HttpMethod, HttpHeader, CacheStatus, HttpResource,
)

_TTL = 3600

_LIST_SQL = """
    SELECT DISTINCT ON (n.topic_id)
        n.newsletter_id, n.topic_id, n.date, n.title
    FROM newsletters n
    JOIN subscriptions s ON s.topic_id = n.topic_id
    WHERE s.user_id = %s
    ORDER BY n.topic_id, n.date DESC
"""

_GET_SQL = """
    SELECT
        n.newsletter_id, n.date, n.title, n.narrative,
        ne.position,
        e.event_id, e.headline, e.summary, e.date AS event_date,
        ne.thread_id, t.name AS thread_name,
        etm.previous_event_id
    FROM newsletters n
    JOIN newsletter_events ne  ON ne.newsletter_id = n.newsletter_id
    JOIN news_events e          ON e.event_id = ne.event_id
    JOIN event_thread_memberships etm
        ON etm.event_id = e.event_id AND etm.thread_id = ne.thread_id
    JOIN threads t              ON t.thread_id = ne.thread_id
    WHERE n.newsletter_id = %s
    ORDER BY ne.position
"""

_LINKS_SQL = """
    SELECT ncl.reason, ncl.position, n2.newsletter_id, n2.date, n2.title
    FROM newsletter_context_links ncl
    JOIN newsletters n2 ON n2.newsletter_id = ncl.linked_newsletter_id
    WHERE ncl.newsletter_id = %s
    ORDER BY ncl.position
"""


def handler(event, context):
    if event.get(LambdaEvent.RESOURCE) == HttpResource.HEALTH:
        return ok({"status": "ok"})
    if "{newsletter_id}" in event.get(LambdaEvent.RESOURCE, "") and event[LambdaEvent.HTTP_METHOD] == HttpMethod.GET:
        return _get_by_id(event)
    if event[LambdaEvent.HTTP_METHOD] == HttpMethod.GET:
        return _list(event)
    return {LambdaResponse.STATUS_CODE: 405, LambdaResponse.BODY: json.dumps({"error": "Method not allowed"})}


def _user_id(event):
    return event[LambdaEvent.REQUEST_CONTEXT][LambdaEvent.AUTHORIZER][LambdaEvent.CLAIMS][LambdaEvent.SUB]


def _list(event):
    user_id = _user_id(event)
    key = f"{CachePrefix.USER_LATEST}{user_id}:latest"
    hit = cache.cache_get(key)
    if hit is not None:
        return ok(hit, {HttpHeader.X_CACHE: CacheStatus.HIT})

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_LIST_SQL, (user_id,))
        rows = [dict(r) for r in cur.fetchall()]

    cache.cache_set(key, rows, ttl=_TTL)
    return ok(rows, {HttpHeader.X_CACHE: CacheStatus.MISS})


def _get_by_id(event):
    newsletter_id = event[LambdaEvent.PATH_PARAMETERS][NewsletterField.ID]
    key = f"{CachePrefix.NEWSLETTER}{newsletter_id}"
    hit = cache.cache_get(key)
    if hit is not None:
        return ok(hit, {HttpHeader.X_CACHE: CacheStatus.HIT})

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_GET_SQL, (newsletter_id,))
        rows = cur.fetchall()
        if not rows:
            return not_found("Newsletter not found")
        cur.execute(_LINKS_SQL, (newsletter_id,))
        links = [dict(r) for r in cur.fetchall()]

    first = dict(rows[0])
    result = {
        NewsletterField.ID: str(first[NewsletterField.ID]),
        NewsletterField.DATE: str(first[NewsletterField.DATE]),
        NewsletterField.TITLE: first[NewsletterField.TITLE],
        NewsletterField.NARRATIVE: first[NewsletterField.NARRATIVE],
        NewsletterField.CONTEXT_LINKS: [
            {
                **dict(r),
                ContextLinkField.NEWSLETTER_ID: str(dict(r)[ContextLinkField.NEWSLETTER_ID]),
                ContextLinkField.DATE: str(dict(r)[ContextLinkField.DATE]),
            }
            for r in links
        ],
        NewsletterField.EVENTS: [
            {
                EventField.POSITION: dict(r)[EventField.POSITION],
                EventField.ID: str(dict(r)[EventField.ID]),
                EventField.HEADLINE: dict(r)[EventField.HEADLINE],
                EventField.SUMMARY: dict(r)[EventField.SUMMARY],
                EventField.EVENT_DATE: str(dict(r)[EventField.EVENT_DATE]),
                EventField.THREAD_ID: str(dict(r)[EventField.THREAD_ID]),
                EventField.THREAD_NAME: dict(r)[EventField.THREAD_NAME],
                EventField.PREVIOUS_EVENT_ID: str(dict(r)[EventField.PREVIOUS_EVENT_ID]) if dict(r)[EventField.PREVIOUS_EVENT_ID] else None,
            }
            for r in rows
        ],
    }
    cache.cache_set(key, result, ttl=_TTL)
    return ok(result, {HttpHeader.X_CACHE: CacheStatus.MISS})
