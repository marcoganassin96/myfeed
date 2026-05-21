from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from handlers import deep_dive, interactions, newsletters, subscriptions
from settings import load


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load()
    mdg_cfg = cfg["mdg"]
    app.state.mdg_client = httpx.AsyncClient(
        base_url=mdg_cfg["url"],
        timeout=httpx.Timeout(
            connect=mdg_cfg["connect_timeout"],
            read=mdg_cfg["read_timeout"],
            write=mdg_cfg["write_timeout"],
            pool=mdg_cfg["pool_timeout"],
        ),
    )
    yield
    await app.state.mdg_client.aclose()


app = FastAPI(lifespan=lifespan)

app.include_router(newsletters.router)
app.include_router(subscriptions.router)
app.include_router(interactions.router)
app.include_router(deep_dive.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
