import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dependencies import get_mdg_client, get_user_id
from fields import HttpHeader, InteractionField, InteractionType
import mdg as _mdg

router = APIRouter()


class InteractionRequest(BaseModel):
    event_id: str
    type: InteractionType


@router.post("/interactions", status_code=201)
async def create_interaction(
    body: InteractionRequest,
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.post(
            "/master-data/interactions",
            json={
                InteractionField.EVENT_ID: body.event_id,
                InteractionField.TYPE: body.type,
            },
            headers={HttpHeader.X_USER_ID: user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    return _mdg.map_response(resp)
