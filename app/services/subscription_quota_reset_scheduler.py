import asyncio
import logging
import os
from typing import Any

from app.services.sub2api_client import Sub2ApiClient
from app.services.subscription_quota_reset import SubscriptionQuotaResetService
from app.services.subscription_quota_reset_state import SubscriptionQuotaResetStateStore

LOGGER = logging.getLogger("uvicorn.error").getChild(__name__)
DEFAULT_INTERVAL_SECONDS = 1800
DEFAULT_STATE_FILE = "data/subscription_quota_reset_state.json"


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


def get_auto_reset_state_file() -> str:
    value = os.getenv("AUTO_RESET_STATE_FILE", DEFAULT_STATE_FILE).strip()
    if not value:
        raise ValueError("AUTO_RESET_STATE_FILE 不能为空")
    return value


async def execute_subscription_quota_reset() -> dict[str, Any]:
    async with Sub2ApiClient() as client:
        state_store = SubscriptionQuotaResetStateStore(get_auto_reset_state_file())
        return await SubscriptionQuotaResetService(client, state_store).run()


async def run_scheduled_auto_reset() -> None:
    try:
        result = await execute_subscription_quota_reset()
        accounts = result["accounts"]
        groups = result["groups"]
        state = result["state"]
        subscriptions = result["subscriptions"]
        LOGGER.info(
            "订阅配额自动重置完成：账号 %s，有效窗口 %s，未锚定窗口 %s，"
            "分组 %s，状态账号 %s，订阅匹配 %s，重置 %s，跳过 %s，失败 %s，"
            "错误 %s",
            accounts["matched"],
            accounts["with_7d_window"],
            accounts["unanchored_7d_window"],
            groups["with_reset_boundary"],
            state["tracked_accounts"],
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
