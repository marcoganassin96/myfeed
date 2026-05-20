import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dependencies import get_mdg_client, get_user_id
from fields import SubscriptionField
import mdg as _mdg

router = APIRouter()


class SubscribeRequest(BaseModel):
    topic_id: str


@router.get("/subscriptions")
async def list_subscriptions(
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.get(
            "/master-data/subscriptions",
            headers={"X-User-Id": user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    return _mdg.map_response(resp)


@router.post("/subscriptions", status_code=201)
async def subscribe(
    body: SubscribeRequest,
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.post(
            "/master-data/subscriptions",
            json={SubscriptionField.TOPIC_ID: body.topic_id},
            headers={"X-User-Id": user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    return _mdg.map_response(resp)


@router.delete("/subscriptions/{topic_id}", status_code=204)
async def unsubscribe(
    topic_id: str,
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.delete(
            f"/master-data/subscriptions/{topic_id}",
            headers={"X-User-Id": user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    if resp.status_code >= 500:
        return JSONResponse({"error": "Bad gateway"}, status_code=502)
    return Response(status_code=204)
