import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dependencies import get_pool, get_user_id
from fields import InteractionField, InteractionType

router = APIRouter()

_INSERT_SQL = """
    INSERT INTO interactions (user_id, event_id, type) VALUES ($1, $2, $3)
    RETURNING interaction_id, created_at
"""


class InteractionRequest(BaseModel):
    event_id: str
    type: InteractionType


@router.post("/interactions", status_code=201)
async def create_interaction(
    body: InteractionRequest,
    user_id: str = Depends(get_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    row = await pool.fetchrow(_INSERT_SQL, user_id, body.event_id, body.type)
    r = dict(row)
    return JSONResponse(
        {
            InteractionField.ID: str(r[InteractionField.ID]),
            InteractionField.CREATED_AT: str(r[InteractionField.CREATED_AT]),
        },
        status_code=201,
    )
