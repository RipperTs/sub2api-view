from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from fastapi import HTTPException

from app.services.sub2api_client import Sub2ApiClient
from app.services.subscription_quota_reset_state import (
    SubscriptionQuotaResetStateError,
    SubscriptionQuotaResetStateStore,
)

PAGE_SIZE = 1000
SEVEN_DAYS = timedelta(days=7)
SEVEN_DAY_SECONDS = int(SEVEN_DAYS.total_seconds())
UNANCHORED_WINDOW_TOLERANCE_SECONDS = 60


@dataclass(frozen=True)
class SevenDayWindow:
    reset_at: datetime
    unanchored: bool


class SubscriptionQuotaResetService:
    def __init__(
        self,
        client: Sub2ApiClient,
        state_store: SubscriptionQuotaResetStateStore | None = None,
    ) -> None:
        self.client = client
        self.state_store = state_store

    async def run(self, now: datetime | None = None) -> dict[str, Any]:
        fixed_now = normalize_datetime(now) if now is not None else None
        checked_at = fixed_now or datetime.now(timezone.utc)
        accounts = await self._list_all(
            self.client.list_accounts,
            {"platform": "openai", "type": "oauth", "sort_order": "asc"},
        )

        errors: list[dict[str, Any]] = []
        state_load_failed = 0
        state_save_failed = 0
        account_states: dict[str, dict[str, Any]] = {}
        if self.state_store is not None:
            try:
                account_states = self.state_store.load()
            except SubscriptionQuotaResetStateError as exc:
                state_load_failed = 1
                errors.append(build_state_error("state_load", exc))

        group_boundaries: dict[int, datetime] = {}
        account_usage_failures = 0
        matched_accounts = 0
        accounts_with_window = 0
        unanchored_accounts = 0

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

            observed_at = fixed_now or datetime.now(timezone.utc)
            state_key = str(account_id)
            reset_boundary, account_state, unanchored = resolve_reset_boundary(
                usage,
                account,
                account_states.get(state_key),
                observed_at,
            )
            if account_state is not None:
                account_states[state_key] = account_state
            if reset_boundary is None:
                if unanchored:
                    unanchored_accounts += 1
                continue

            accounts_with_window += 1
            for group_id in get_group_ids(account):
                previous = group_boundaries.get(group_id)
                if previous is None or reset_boundary > previous:
                    group_boundaries[group_id] = reset_boundary

        if self.state_store is not None:
            try:
                self.state_store.save(account_states)
            except SubscriptionQuotaResetStateError as exc:
                state_save_failed = 1
                errors.append(build_state_error("state_save", exc))
                group_boundaries.clear()

        subscriptions: dict[int, tuple[dict[str, Any], datetime]] = {}
        group_list_failures = 0
        for group_id, reset_boundary in group_boundaries.items():
            try:
                group_subscriptions = await self._list_all(
                    self.client.list_subscriptions,
                    {"group_id": group_id, "status": "active", "sort_order": "asc"},
                )
            except Exception as exc:
                group_list_failures += 1
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
                "unanchored_7d_window": unanchored_accounts,
                "usage_refresh_failed": account_usage_failures,
            },
            "groups": {
                "with_reset_boundary": len(group_boundaries),
                "subscription_list_failed": group_list_failures,
            },
            "state": {
                "tracked_accounts": len(account_states),
                "load_failed": state_load_failed,
                "save_failed": state_save_failed,
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
    boundaries: list[datetime] = []

    extra = account.get("extra")
    if isinstance(extra, dict):
        add_reset_boundary(
            boundaries,
            extra.get("codex_7d_reset_at"),
            now,
            is_unanchored_seven_day_window(
                extra.get("codex_7d_used_percent"),
                extra.get("codex_7d_reset_after_seconds"),
            ),
        )

    seven_day = usage.get("seven_day")
    if isinstance(seven_day, dict):
        add_reset_boundary(
            boundaries,
            seven_day.get("resets_at"),
            now,
            is_unanchored_seven_day_window(
                seven_day.get("utilization"),
                seven_day.get("remaining_seconds"),
            ),
        )

    return max(boundaries) if boundaries else None


def resolve_reset_boundary(
    usage: dict[str, Any],
    account: dict[str, Any],
    previous_state: dict[str, Any] | None,
    now: datetime,
) -> tuple[datetime | None, dict[str, Any] | None, bool]:
    usage_window = get_usage_window(usage)
    account_window = get_account_window(account)
    current_window = usage_window or account_window
    fallback_boundary = get_reset_boundary(usage, account, now)

    if current_window is None:
        previous_boundary = get_state_datetime(previous_state, "last_boundary")
        boundary = latest_datetime(fallback_boundary, previous_boundary)
        return boundary, previous_state, False

    previous_mode = previous_state.get("mode") if previous_state else None
    previous_boundary = get_state_datetime(previous_state, "last_boundary")

    if current_window.unanchored:
        # Freeze the first rolling boundary and reuse it on later probes.
        if previous_mode == "anchored":
            boundary = min(current_window.reset_at - SEVEN_DAYS, now)
        elif previous_mode == "unanchored":
            boundary = previous_boundary
        else:
            boundary = fallback_boundary
    else:
        boundary = get_window_boundary(current_window.reset_at, now)

    boundary = latest_datetime(boundary, previous_boundary)
    boundary = latest_datetime(boundary, fallback_boundary)
    state = {
        "mode": "unanchored" if current_window.unanchored else "anchored",
        "reset_at": current_window.reset_at.isoformat(),
        "last_boundary": boundary.isoformat() if boundary is not None else None,
        "observed_at": now.isoformat(),
    }
    return boundary, state, current_window.unanchored


def get_usage_window(usage: dict[str, Any]) -> SevenDayWindow | None:
    seven_day = usage.get("seven_day")
    if not isinstance(seven_day, dict):
        return None
    return build_window(
        seven_day.get("resets_at"),
        seven_day.get("utilization"),
        seven_day.get("remaining_seconds"),
    )


def get_account_window(account: dict[str, Any]) -> SevenDayWindow | None:
    extra = account.get("extra")
    if not isinstance(extra, dict):
        return None
    return build_window(
        extra.get("codex_7d_reset_at"),
        extra.get("codex_7d_used_percent"),
        extra.get("codex_7d_reset_after_seconds"),
    )


def build_window(
    reset_at: Any,
    utilization: Any,
    remaining_seconds: Any,
) -> SevenDayWindow | None:
    parsed_reset_at = parse_datetime(reset_at)
    if parsed_reset_at is None:
        return None
    return SevenDayWindow(
        reset_at=parsed_reset_at,
        unanchored=is_unanchored_seven_day_window(
            utilization,
            remaining_seconds,
        ),
    )


def get_window_boundary(reset_at: datetime, now: datetime) -> datetime | None:
    boundary = reset_at if reset_at <= now else reset_at - SEVEN_DAYS
    return boundary if boundary <= now else None


def get_state_datetime(
    state: dict[str, Any] | None,
    key: str,
) -> datetime | None:
    return parse_datetime(state.get(key)) if state is not None else None


def latest_datetime(
    first: datetime | None,
    second: datetime | None,
) -> datetime | None:
    candidates = [value for value in (first, second) if value is not None]
    return max(candidates) if candidates else None


def add_reset_boundary(
    boundaries: list[datetime],
    reset_at: Any,
    now: datetime,
    unanchored: bool,
) -> None:
    parsed_reset_at = parse_datetime(reset_at)
    if parsed_reset_at is None:
        return

    if parsed_reset_at <= now:
        boundaries.append(parsed_reset_at)
    elif not unanchored:
        boundary = parsed_reset_at - SEVEN_DAYS
        if boundary <= now:
            boundaries.append(boundary)


def is_unanchored_seven_day_window(
    utilization: Any,
    remaining_seconds: Any,
) -> bool:
    # An unused OpenAI window can roll forward on every probe, so it has no
    # stable cycle boundary until usage begins or the previous snapshot expires.
    parsed_utilization = parse_number(utilization)
    parsed_remaining = parse_number(remaining_seconds)
    if parsed_utilization is None or parsed_remaining is None:
        return False

    return (
        parsed_utilization <= 0
        and parsed_remaining
        >= SEVEN_DAY_SECONDS - UNANCHORED_WINDOW_TOLERANCE_SECONDS
    )


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


def parse_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


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


def build_state_error(scope: str, exc: Exception) -> dict[str, Any]:
    return {"scope": scope, "message": str(exc)}
