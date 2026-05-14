import asyncio
import json
import os

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dependencies import get_user_id
from fields import DeepDiveField, EnvVar

router = APIRouter()

_DEFAULT_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]


def get_deep_dive_chunks() -> list[str]:
    return _DEFAULT_CHUNKS


def get_chunk_interval() -> float:
    return float(os.environ.get(EnvVar.DEEP_DIVE_INTERVAL, "0.05"))


async def _sse_stream(chunks: list[str], interval: float):
    for chunk in chunks:
        yield f"data: {json.dumps({DeepDiveField.CHUNK: chunk, DeepDiveField.DONE: False})}\n\n"
        await asyncio.sleep(interval)
    yield f"data: {json.dumps({DeepDiveField.CHUNK: '', DeepDiveField.DONE: True})}\n\n"


@router.post("/deep-dive/{event_id}")
async def deep_dive(
    event_id: str,
    user_id: str = Depends(get_user_id),
    chunks: list[str] = Depends(get_deep_dive_chunks),
    interval: float = Depends(get_chunk_interval),
):
    return StreamingResponse(
        _sse_stream(chunks, interval),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
