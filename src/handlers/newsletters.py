import json
import os
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from dependencies import get_pool, get_redis, get_user_id
from fields import (
    CachePrefix, CacheStatus, ContextLinkField,
    EnvVar, EventField, HttpHeader, NewsletterField,
)

router = APIRouter()

_TTL = 3600
_bypass_allowed = os.environ.get(EnvVar.ALLOW_CACHE_BYPASS, "false").lower() == "true"

_LIST_SQL = """
    SELECT DISTINCT ON (n.topic_id)
        n.newsletter_id, n.topic_id, n.date, n.title
    FROM newsletters n
    JOIN subscriptions s ON s.topic_id = n.topic_id
    WHERE s.user_id = $1
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
    WHERE n.newsletter_id = $1
    ORDER BY ne.position
"""

_LINKS_SQL = """
    SELECT ncl.reason, ncl.position, n2.newsletter_id, n2.date, n2.title
    FROM newsletter_context_links ncl
    JOIN newsletters n2 ON n2.newsletter_id = ncl.linked_newsletter_id
    WHERE ncl.newsletter_id = $1
    ORDER BY ncl.position
"""


@router.get("/newsletters")
async def list_newsletters(
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    redis=Depends(get_redis),
):
    key = f"{CachePrefix.USER_LATEST}{user_id}:latest"
    hit = await redis.get(key)
    if hit:
        return JSONResponse(json.loads(hit), headers={HttpHeader.X_CACHE: CacheStatus.HIT})
    rows = await pool.fetch(_LIST_SQL, user_id)
    result = [dict(r) for r in rows]
    await redis.set(key, json.dumps(result, default=str), ex=_TTL)
    return JSONResponse(result, headers={HttpHeader.X_CACHE: CacheStatus.MISS})


@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: UUID,
    request: Request,
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    redis=Depends(get_redis),
):
    bypass = _bypass_allowed and request.headers.get(HttpHeader.X_BYPASS_CACHE) == "1"
    key = f"{CachePrefix.NEWSLETTER}{newsletter_id}"

    if not bypass:
        hit = await redis.get(key)
        if hit:
            return JSONResponse(json.loads(hit), headers={HttpHeader.X_CACHE: CacheStatus.HIT})

    rows = await pool.fetch(_GET_SQL, newsletter_id)
    if not rows:
        return JSONResponse({"error": "Newsletter not found"}, status_code=404)
    links = await pool.fetch(_LINKS_SQL, newsletter_id)

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
                EventField.PREVIOUS_EVENT_ID: (
                    str(dict(r)[EventField.PREVIOUS_EVENT_ID])
                    if dict(r)[EventField.PREVIOUS_EVENT_ID] else None
                ),
            }
            for r in rows
        ],
    }

    if not bypass:
        await redis.set(key, json.dumps(result, default=str), ex=_TTL)

    return JSONResponse(result, headers={HttpHeader.X_CACHE: CacheStatus.MISS})
