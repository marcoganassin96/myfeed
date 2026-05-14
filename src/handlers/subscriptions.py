import asyncpg
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dependencies import get_pool, get_user_id
from fields import SubscriptionField, TopicField

router = APIRouter()

_LIST_SQL = """
    SELECT s.topic_id, t.name, s.subscribed_at
    FROM subscriptions s JOIN topics t ON t.topic_id = s.topic_id
    WHERE s.user_id = $1 ORDER BY s.subscribed_at DESC
"""
_INSERT_SQL = """
    INSERT INTO subscriptions (user_id, topic_id) VALUES ($1, $2)
    ON CONFLICT (user_id, topic_id) DO NOTHING
    RETURNING topic_id,
        (SELECT name FROM topics WHERE topic_id = $2) AS name,
        subscribed_at
"""
_DELETE_SQL = "DELETE FROM subscriptions WHERE user_id = $1 AND topic_id = $2"


class SubscribeRequest(BaseModel):
    topic_id: str


@router.get("/subscriptions")
async def list_subscriptions(
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    rows = await pool.fetch(_LIST_SQL, user_id)
    return JSONResponse([
        {
            **dict(r),
            SubscriptionField.TOPIC_ID: str(dict(r)[SubscriptionField.TOPIC_ID]),
            SubscriptionField.SUBSCRIBED_AT: str(dict(r)[SubscriptionField.SUBSCRIBED_AT]),
        }
        for r in rows
    ])


@router.post("/subscriptions", status_code=201)
async def subscribe(
    body: SubscribeRequest,
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    row = await pool.fetchrow(_INSERT_SQL, user_id, body.topic_id)
    r = dict(row)
    return JSONResponse(
        {
            **r,
            SubscriptionField.TOPIC_ID: str(r[SubscriptionField.TOPIC_ID]),
            SubscriptionField.SUBSCRIBED_AT: str(r.get(SubscriptionField.SUBSCRIBED_AT, "")),
        },
        status_code=201,
    )


@router.delete("/subscriptions/{topic_id}", status_code=204)
async def unsubscribe(
    topic_id: str,
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    await pool.execute(_DELETE_SQL, user_id, topic_id)
    return Response(status_code=204)
