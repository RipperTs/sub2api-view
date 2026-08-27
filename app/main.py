import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.pages import router as pages_router
from app.services.subscription_quota_reset_scheduler import (
    get_auto_reset_interval_seconds,
    is_auto_reset_enabled,
    run_auto_reset_scheduler,
)

LOGGER = logging.getLogger("uvicorn.error").getChild(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    scheduler_task: asyncio.Task[None] | None = None
    if is_auto_reset_enabled():
        interval_seconds = get_auto_reset_interval_seconds()
        scheduler_task = asyncio.create_task(run_auto_reset_scheduler(interval_seconds))
        LOGGER.info("订阅配额自动重置任务已启动，执行间隔 %s 秒", interval_seconds)

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(title="sub2api-view", lifespan=lifespan)


@app.middleware("http")
async def allow_iframe_embedding(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(api_router)
app.include_router(pages_router)
