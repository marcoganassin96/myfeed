import asyncio
import json
import os

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dependencies import get_mdg_client, get_user_id
from fields import DeepDiveField, EnvVar, HttpHeader

router = APIRouter()

_DEFAULT_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]

_SSE_HEADERS = {str(HttpHeader.CACHE_CONTROL): "no-cache", str(HttpHeader.X_ACCEL_BUFFERING): "no"}


def get_deep_dive_chunks() -> list[str]:
    return _DEFAULT_CHUNKS


def get_chunk_interval() -> float:
    return float(os.environ.get(EnvVar.DEEP_DIVE_INTERVAL, "0.05"))


async def _sse_stream(chunks: list[str], interval: float):
    for chunk in chunks:
        yield f"data: {json.dumps({DeepDiveField.CHUNK: chunk, DeepDiveField.DONE: False})}\n\n"
        await asyncio.sleep(interval)
    yield f"data: {json.dumps({DeepDiveField.CHUNK: '', DeepDiveField.DONE: True})}\n\n"


async def _sse_stream_and_persist(
    chunks: list[str],
    interval: float,
    event_id: str,
    user_id: str,
    client: httpx.AsyncClient,
):
    async for frame in _sse_stream(chunks, interval):
        yield frame
    try:
        await client.post(
            f"/master-data/deep-dive/{event_id}",
            json={"chunks": chunks},
            headers={HttpHeader.X_USER_ID: user_id},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        pass


@router.post("/deep-dive/{event_id}")
async def deep_dive(
    event_id: str,
    client: httpx.AsyncClient | None = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
    chunks: list[str] = Depends(get_deep_dive_chunks),
    interval: float = Depends(get_chunk_interval),
):
    if client is None:
        return StreamingResponse(
            _sse_stream(chunks, interval),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    try:
        cache_resp = await client.get(
            f"/master-data/deep-dive/{event_id}",
            headers={HttpHeader.X_USER_ID: user_id},
        )
        if cache_resp.status_code == 200:
            cached = cache_resp.json().get("chunks", [])
            return StreamingResponse(
                _sse_stream(cached, 0.0),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        return StreamingResponse(
            _sse_stream(chunks, interval),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    return StreamingResponse(
        _sse_stream_and_persist(chunks, interval, event_id, user_id, client),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
