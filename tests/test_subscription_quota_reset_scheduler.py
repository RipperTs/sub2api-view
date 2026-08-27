import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from app.main import app, lifespan
from app.services.subscription_quota_reset_scheduler import (
    DEFAULT_INTERVAL_SECONDS,
    LOGGER,
    get_auto_reset_interval_seconds,
    is_auto_reset_enabled,
    run_auto_reset_scheduler,
    run_scheduled_auto_reset,
)


class SubscriptionQuotaResetSchedulerTest(unittest.IsolatedAsyncioTestCase):
    def test_uses_enabled_thirty_minute_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(is_auto_reset_enabled())
            self.assertEqual(get_auto_reset_interval_seconds(), DEFAULT_INTERVAL_SECONDS)

    def test_can_disable_auto_reset(self) -> None:
        with patch.dict(os.environ, {"AUTO_RESET_ENABLED": "false"}):
            self.assertFalse(is_auto_reset_enabled())

    def test_does_not_expose_manual_reset_endpoint(self) -> None:
        self.assertNotIn("/api/subscriptions/auto-reset", app.openapi()["paths"])

    def test_rejects_invalid_interval(self) -> None:
        for value in ("0", "-1", "invalid"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"AUTO_RESET_INTERVAL_SECONDS": value},
            ):
                with self.assertRaisesRegex(ValueError, "必须是正整数"):
                    get_auto_reset_interval_seconds()

    async def test_logs_failure_without_stopping_scheduler(self) -> None:
        execute = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

        with patch(
            "app.services.subscription_quota_reset_scheduler.execute_subscription_quota_reset",
            execute,
        ), self.assertLogs(LOGGER, level="ERROR"):
            await run_scheduled_auto_reset()

        execute.assert_awaited_once_with()

    async def test_logs_account_group_and_subscription_summary(self) -> None:
        execute = AsyncMock(return_value={
            "accounts": {
                "matched": 2,
                "with_7d_window": 1,
                "unanchored_7d_window": 1,
            },
            "groups": {"with_reset_boundary": 1},
            "subscriptions": {
                "matched": 4,
                "reset": 4,
                "skipped": 0,
                "failed": 0,
            },
            "errors": [],
        })

        with patch(
            "app.services.subscription_quota_reset_scheduler.execute_subscription_quota_reset",
            execute,
        ), self.assertLogs(LOGGER, level="INFO") as logs:
            await run_scheduled_auto_reset()

        self.assertIn("未锚定窗口 1", logs.output[0])
        self.assertIn("分组 1", logs.output[0])
        self.assertIn("重置 4", logs.output[0])

    async def test_runs_immediately_then_waits_for_interval(self) -> None:
        run_once = AsyncMock()
        sleep = AsyncMock(side_effect=asyncio.CancelledError)

        with patch(
            "app.services.subscription_quota_reset_scheduler.run_scheduled_auto_reset",
            run_once,
        ), patch(
            "app.services.subscription_quota_reset_scheduler.asyncio.sleep",
            sleep,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await run_auto_reset_scheduler(1800)

        run_once.assert_awaited_once_with()
        sleep.assert_awaited_once_with(1800)

    async def test_lifespan_starts_and_stops_scheduler(self) -> None:
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def run_scheduler(interval_seconds: int) -> None:
            self.assertEqual(interval_seconds, 1800)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        with patch("app.main.is_auto_reset_enabled", return_value=True), patch(
            "app.main.get_auto_reset_interval_seconds",
            return_value=1800,
        ), patch("app.main.run_auto_reset_scheduler", side_effect=run_scheduler):
            async with lifespan(app):
                await asyncio.wait_for(started.wait(), timeout=1)

        self.assertTrue(stopped.is_set())


if __name__ == "__main__":
    unittest.main()
