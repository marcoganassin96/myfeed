from contextlib import asynccontextmanager

from fastapi import FastAPI

import cache_async
import db_async
from handlers import deep_dive, interactions, newsletters, subscriptions


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await db_async.create_pool()
    app.state.redis = await cache_async.create_redis()
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)

app.include_router(newsletters.router)
app.include_router(subscriptions.router)
app.include_router(interactions.router)
app.include_router(deep_dive.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
