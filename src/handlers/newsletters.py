import httpx
from fastapi import APIRouter, Depends

from dependencies import get_mdg_client, get_user_id
import mdg as _mdg

router = APIRouter()


@router.get("/newsletters")
async def list_newsletters(
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.get(
            "/master-data/newsletters",
            headers={"X-User-Id": user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    return _mdg.map_response(resp)


@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: str,
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    if client is None:
        return _mdg.unavailable()
    try:
        resp = await client.get(
            f"/master-data/newsletters/{newsletter_id}",
            headers={"X-User-Id": user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return _mdg.unavailable()
    return _mdg.map_response(resp)
