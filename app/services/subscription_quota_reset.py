from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.services.sub2api_client import Sub2ApiClient

PAGE_SIZE = 1000
SEVEN_DAYS = timedelta(days=7)


class SubscriptionQuotaResetService:
    def __init__(self, client: Sub2ApiClient) -> None:
        self.client = client

    async def run(self, now: datetime | None = None) -> dict[str, Any]:
        checked_at = normalize_datetime(now or datetime.now(timezone.utc))
        accounts = await self._list_all(
            self.client.list_accounts,
            {"platform": "openai", "type": "oauth", "sort_order": "asc"},
        )

        group_boundaries: dict[int, datetime] = {}
        account_usage_failures = 0
        matched_accounts = 0
        accounts_with_window = 0
        errors: list[dict[str, Any]] = []

        for account in accounts:
            if account.get("platform") != "openai" or account.get("type") != "oauth":
                continue

            account_id = positive_int(account.get("id"))
            if account_id is None:
                continue
            matched_accounts += 1

            usage: dict[str, Any] = {}
            try:
                payload = await self.client.get_account_usage(account_id, force=True)
                data = unwrap_data(payload)
                if isinstance(data, dict):
                    usage = data
            except Exception as exc:  # Continue with the account snapshot when refresh fails.
                account_usage_failures += 1
                errors.append(build_error("account_usage", account_id, exc))

            reset_boundary = get_reset_boundary(usage, account, checked_at)
            if reset_boundary is None:
                continue

            accounts_with_window += 1
            for group_id in get_group_ids(account):
                previous = group_boundaries.get(group_id)
                if previous is None or reset_boundary > previous:
                    group_boundaries[group_id] = reset_boundary

        subscriptions: dict[int, tuple[dict[str, Any], datetime]] = {}
        for group_id, reset_boundary in group_boundaries.items():
            try:
                group_subscriptions = await self._list_all(
                    self.client.list_subscriptions,
                    {"group_id": group_id, "status": "active", "sort_order": "asc"},
                )
            except Exception as exc:
                errors.append(build_error("subscription_list", group_id, exc))
                continue

            for subscription in group_subscriptions:
                subscription_id = positive_int(subscription.get("id"))
                if (
                    subscription_id is None
                    or subscription.get("status") != "active"
                    or positive_int(subscription.get("group_id")) != group_id
                ):
                    continue

                existing = subscriptions.get(subscription_id)
                if existing is None or reset_boundary > existing[1]:
                    subscriptions[subscription_id] = (subscription, reset_boundary)

        reset_ids: list[int] = []
        skipped = 0
        reset_failures = 0

        for subscription_id, (subscription, reset_boundary) in subscriptions.items():
            window_start = parse_datetime(
                subscription.get("weekly_window_start") or subscription.get("starts_at")
            )
            if window_start is None:
                skipped += 1
                errors.append({
                    "scope": "subscription_window",
                    "id": subscription_id,
                    "message": "订阅缺少有效的 weekly_window_start 和 starts_at",
                })
                continue

            if window_start >= reset_boundary:
                skipped += 1
                continue

            try:
                await self.client.reset_subscription_quota(subscription_id)
                reset_ids.append(subscription_id)
            except Exception as exc:
                reset_failures += 1
                errors.append(build_error("subscription_reset", subscription_id, exc))

        return {
            "checked_at": checked_at.isoformat(),
            "accounts": {
                "matched": matched_accounts,
                "with_7d_window": accounts_with_window,
                "usage_refresh_failed": account_usage_failures,
            },
            "subscriptions": {
                "matched": len(subscriptions),
                "reset": len(reset_ids),
                "skipped": skipped,
                "failed": reset_failures,
            },
            "reset_subscription_ids": reset_ids,
            "errors": errors,
        }

    async def _list_all(
        self,
        fetch: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []

        while True:
            payload = await fetch({**params, "page": page, "page_size": PAGE_SIZE})
            data = unwrap_data(payload)

            if isinstance(data, list):
                items.extend(item for item in data if isinstance(item, dict))
                break
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise HTTPException(status_code=502, detail="Sub2API 分页响应格式异常")

            page_items = data["items"]
            items.extend(item for item in page_items if isinstance(item, dict))

            pages = positive_int(data.get("pages"))
            if pages is not None:
                if page >= pages:
                    break
            elif len(page_items) < PAGE_SIZE:
                break
            page += 1

        return items


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def get_reset_boundary(
    usage: dict[str, Any],
    account: dict[str, Any],
    now: datetime,
) -> datetime | None:
    seven_day = usage.get("seven_day")
    reset_at = seven_day.get("resets_at") if isinstance(seven_day, dict) else None

    if reset_at is None:
        extra = account.get("extra")
        if isinstance(extra, dict):
            reset_at = extra.get("codex_7d_reset_at")

    parsed_reset_at = parse_datetime(reset_at)
    if parsed_reset_at is None:
        return None

    boundary = parsed_reset_at - SEVEN_DAYS if parsed_reset_at > now else parsed_reset_at
    return boundary if boundary <= now else None


def get_group_ids(account: dict[str, Any]) -> set[int]:
    group_ids = account.get("group_ids")
    if not isinstance(group_ids, list):
        return set()
    return {group_id for value in group_ids if (group_id := positive_int(value)) is not None}


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return normalize_datetime(datetime.fromisoformat(candidate))
    except ValueError:
        return None


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_error(scope: str, item_id: int, exc: Exception) -> dict[str, Any]:
    message = exc.detail if isinstance(exc, HTTPException) else str(exc)
    return {"scope": scope, "id": item_id, "message": str(message)}
