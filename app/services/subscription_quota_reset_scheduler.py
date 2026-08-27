import asyncio
import logging
import os
from typing import Any

from app.services.sub2api_client import Sub2ApiClient
from app.services.subscription_quota_reset import SubscriptionQuotaResetService

LOGGER = logging.getLogger("uvicorn.error").getChild(__name__)
DEFAULT_INTERVAL_SECONDS = 1800


def is_auto_reset_enabled() -> bool:
    value = os.getenv("AUTO_RESET_ENABLED", "true")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_auto_reset_interval_seconds() -> int:
    value = os.getenv("AUTO_RESET_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        interval = int(value)
    except ValueError as exc:
        raise ValueError("AUTO_RESET_INTERVAL_SECONDS 必须是正整数") from exc

    if interval <= 0:
        raise ValueError("AUTO_RESET_INTERVAL_SECONDS 必须是正整数")
    return interval


async def execute_subscription_quota_reset() -> dict[str, Any]:
    async with Sub2ApiClient() as client:
        return await SubscriptionQuotaResetService(client).run()


async def run_scheduled_auto_reset() -> None:
    try:
        result = await execute_subscription_quota_reset()
        accounts = result["accounts"]
        groups = result["groups"]
        subscriptions = result["subscriptions"]
        LOGGER.info(
            "订阅配额自动重置完成：账号 %s，有效窗口 %s，未锚定窗口 %s，"
            "分组 %s，订阅匹配 %s，重置 %s，跳过 %s，失败 %s，错误 %s",
            accounts["matched"],
            accounts["with_7d_window"],
            accounts["unanchored_7d_window"],
            groups["with_reset_boundary"],
            subscriptions["matched"],
            subscriptions["reset"],
            subscriptions["skipped"],
            subscriptions["failed"],
            len(result["errors"]),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("订阅配额自动重置执行失败")


async def run_auto_reset_scheduler(interval_seconds: int) -> None:
    while True:
        await run_scheduled_auto_reset()
        await asyncio.sleep(interval_seconds)
