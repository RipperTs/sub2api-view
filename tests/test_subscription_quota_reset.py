import unittest
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.services.subscription_quota_reset import SubscriptionQuotaResetService


class FakeSub2ApiClient:
    def __init__(
        self,
        accounts: list[dict[str, Any]],
        subscriptions: dict[int, list[dict[str, Any]]],
        usage: dict[int, dict[str, Any]],
    ) -> None:
        self.accounts = accounts
        self.subscriptions = subscriptions
        self.usage = usage
        self.usage_errors: set[int] = set()
        self.usage_requests: list[tuple[int, bool]] = []
        self.reset_errors: set[int] = set()
        self.reset_attempts: list[int] = []

    async def list_accounts(self, params: dict[str, Any]) -> dict[str, Any]:
        return paginated(self.accounts)

    async def get_account_usage(
        self,
        account_id: int,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        self.usage_requests.append((account_id, force))
        if account_id in self.usage_errors:
            raise HTTPException(status_code=502, detail="刷新用量失败")
        return {"data": self.usage.get(account_id, {})}

    async def list_subscriptions(self, params: dict[str, Any]) -> dict[str, Any]:
        return paginated(self.subscriptions.get(int(params["group_id"]), []))

    async def reset_subscription_quota(self, subscription_id: int) -> dict[str, Any]:
        self.reset_attempts.append(subscription_id)
        if subscription_id in self.reset_errors:
            raise HTTPException(status_code=502, detail="重置失败")
        return {"data": {"id": subscription_id}}


def paginated(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": 1000,
            "pages": 1,
        }
    }


class SubscriptionQuotaResetServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)

    async def test_resets_only_subscriptions_older_than_latest_window(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[openai_account(1, [10])],
            subscriptions={
                10: [
                    active_subscription(101, 10, "2026-08-04T08:00:00Z"),
                    active_subscription(102, 10, "2026-08-06T08:00:00Z"),
                ]
            },
            usage={1: usage_with_reset("2026-08-12T00:00:00Z")},
        )

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.reset_attempts, [101])
        self.assertEqual(result["subscriptions"], {
            "matched": 2,
            "reset": 1,
            "skipped": 1,
            "failed": 0,
        })

    async def test_resets_subscriptions_in_different_account_groups(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[
                openai_account(1, [10]),
                openai_account(2, [20]),
            ],
            subscriptions={
                10: [active_subscription(101, 10, "2026-08-01T08:00:00Z")],
                20: [active_subscription(201, 20, "2026-08-01T08:00:00Z")],
            },
            usage={
                1: usage_with_reset("2026-08-12T00:00:00Z"),
                2: usage_with_reset("2026-08-13T00:00:00Z"),
            },
        )

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.reset_attempts, [101, 201])
        self.assertEqual(result["groups"]["with_reset_boundary"], 2)
        self.assertEqual(result["subscriptions"]["reset"], 2)

    async def test_uses_expired_snapshot_before_forced_refresh(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[openai_account(
                1,
                [10],
                extra={
                    "codex_7d_used_percent": 100,
                    "codex_7d_reset_after_seconds": 10,
                    "codex_7d_reset_at": "2026-08-09T11:59:00Z",
                },
            )],
            subscriptions={
                10: [active_subscription(101, 10, "2026-08-08T08:00:00Z")],
            },
            usage={1: {
                "seven_day": {
                    "utilization": 0,
                    "resets_at": "2026-08-16T12:00:00Z",
                    "remaining_seconds": 604799,
                },
            }},
        )

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.usage_requests, [(1, True)])
        self.assertEqual(client.reset_attempts, [101])
        self.assertEqual(result["groups"]["with_reset_boundary"], 1)

    async def test_ignores_unanchored_zero_usage_window(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[openai_account(
                1,
                [10],
                extra={
                    "codex_7d_used_percent": 0,
                    "codex_7d_reset_after_seconds": 604799,
                    "codex_7d_reset_at": "2026-08-16T12:00:10Z",
                },
            )],
            subscriptions={
                10: [active_subscription(101, 10, "2026-08-08T08:00:00Z")],
            },
            usage={1: {
                "seven_day": {
                    "utilization": 0,
                    "resets_at": "2026-08-16T12:00:12Z",
                    "remaining_seconds": 604799,
                },
            }},
        )

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.usage_requests, [(1, True)])
        self.assertEqual(client.reset_attempts, [])
        self.assertEqual(result["accounts"]["unanchored_7d_window"], 1)
        self.assertEqual(result["groups"]["with_reset_boundary"], 0)
        self.assertEqual(result["subscriptions"]["matched"], 0)

    async def test_falls_back_to_account_snapshot_when_usage_refresh_fails(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[openai_account(
                1,
                [10],
                extra={"codex_7d_reset_at": "2026-08-09T10:00:00Z"},
            )],
            subscriptions={10: [active_subscription(101, 10, "2026-08-08T08:00:00Z")]},
            usage={},
        )
        client.usage_errors.add(1)

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.reset_attempts, [101])
        self.assertEqual(result["accounts"]["usage_refresh_failed"], 1)
        self.assertEqual(result["subscriptions"]["reset"], 1)
        self.assertEqual(result["errors"][0]["scope"], "account_usage")

    async def test_deduplicates_subscriptions_and_uses_latest_boundary(self) -> None:
        subscription = active_subscription(101, 10, "2026-08-06T08:00:00Z")
        client = FakeSub2ApiClient(
            accounts=[
                openai_account(1, [10]),
                openai_account(2, [10]),
            ],
            subscriptions={10: [subscription, subscription]},
            usage={
                1: usage_with_reset("2026-08-12T00:00:00Z"),
                2: usage_with_reset("2026-08-14T00:00:00Z"),
            },
        )

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.reset_attempts, [101])
        self.assertEqual(result["subscriptions"]["matched"], 1)
        self.assertEqual(result["subscriptions"]["reset"], 1)

    async def test_continues_after_individual_reset_failure(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[openai_account(1, [10])],
            subscriptions={
                10: [
                    active_subscription(101, 10, "2026-08-01T08:00:00Z"),
                    active_subscription(102, 10, "2026-08-01T08:00:00Z"),
                ]
            },
            usage={1: usage_with_reset("2026-08-12T00:00:00Z")},
        )
        client.reset_errors.add(101)

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(client.reset_attempts, [101, 102])
        self.assertEqual(result["subscriptions"]["reset"], 1)
        self.assertEqual(result["subscriptions"]["failed"], 1)
        self.assertEqual(result["errors"][0]["scope"], "subscription_reset")

    async def test_follows_reported_pagination_when_page_size_is_capped(self) -> None:
        client = FakeSub2ApiClient(
            accounts=[],
            subscriptions={10: [active_subscription(101, 10, "2026-08-01T08:00:00Z")]},
            usage={2: usage_with_reset("2026-08-12T00:00:00Z")},
        )
        requested_pages: list[int] = []

        async def list_accounts(params: dict[str, Any]) -> dict[str, Any]:
            page = int(params["page"])
            requested_pages.append(page)
            account = openai_account(page, [10] if page == 2 else [])
            return {
                "data": {
                    "items": [account],
                    "page": page,
                    "page_size": 1,
                    "pages": 2,
                }
            }

        client.list_accounts = list_accounts

        result = await SubscriptionQuotaResetService(client).run(self.now)

        self.assertEqual(requested_pages, [1, 2])
        self.assertEqual(result["accounts"]["matched"], 2)
        self.assertEqual(client.reset_attempts, [101])


def openai_account(
    account_id: int,
    group_ids: list[int],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": account_id,
        "platform": "openai",
        "type": "oauth",
        "group_ids": group_ids,
        **extra,
    }


def active_subscription(
    subscription_id: int,
    group_id: int,
    weekly_window_start: str,
) -> dict[str, Any]:
    return {
        "id": subscription_id,
        "group_id": group_id,
        "status": "active",
        "starts_at": "2026-07-01T00:00:00Z",
        "weekly_window_start": weekly_window_start,
    }


def usage_with_reset(reset_at: str) -> dict[str, Any]:
    return {"seven_day": {"resets_at": reset_at}}


if __name__ == "__main__":
    unittest.main()
