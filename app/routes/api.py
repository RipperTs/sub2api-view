import asyncio
import re
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import verify_admin_user, verify_api_user
from app.services.sub2api_client import Sub2ApiClient
from app.services.subscription_quota_reset import SubscriptionQuotaResetService

router = APIRouter(prefix="/api")

SENSITIVE_ACCOUNT_KEYS = {
    "credentials",
    "proxy",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "secret",
    "password",
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AUTO_RESET_LOCK = asyncio.Lock()
UPSTREAM_PAGE_SIZE = 100


@router.get("/accounts")
async def list_accounts(
        user: Annotated[dict[str, Any], Depends(verify_api_user)],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        platform: str | None = None,
        account_type: str | None = Query(default=None, alias="type"),
        status: str | None = None,
        search: str | None = None,
):
    group_ids = get_user_group_ids(user)
    if not group_ids:
        return empty_accounts_payload(page, page_size)

    params = {
        "platform": platform,
        "type": account_type,
        "status": status,
        "search": search,
        "sort_order": "asc"
    }
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}

    payload = await list_all_accounts(clean_params)
    filter_and_paginate_accounts(payload, group_ids, page, page_size)
    await enrich_accounts_with_usage(payload)
    return sanitize_accounts_payload(payload)


@router.post(
    "/subscriptions/auto-reset",
    dependencies=[Depends(verify_admin_user)],
)
async def auto_reset_subscription_quotas():
    if AUTO_RESET_LOCK.locked():
        raise HTTPException(status_code=409, detail="自动重置检测正在执行")

    async with AUTO_RESET_LOCK:
        async with Sub2ApiClient() as client:
            return await SubscriptionQuotaResetService(client).run()


async def list_all_accounts(params: dict[str, Any]) -> dict[str, Any]:
    async with Sub2ApiClient() as client:
        first_payload = await client.list_accounts({
            **params,
            "page": 1,
            "page_size": UPSTREAM_PAGE_SIZE,
        })
        first_data = get_accounts_data(first_payload)
        pages = first_data.get("pages", 1)

        if pages > 1:
            remaining_payloads = await asyncio.gather(*(
                client.list_accounts({
                    **params,
                    "page": current_page,
                    "page_size": UPSTREAM_PAGE_SIZE,
                })
                for current_page in range(2, pages + 1)
            ))
            for payload in remaining_payloads:
                first_data["items"].extend(get_accounts_data(payload)["items"])

        return first_payload


def get_user_group_ids(user: dict[str, Any]) -> set[int]:
    allowed_groups = user.get("allowed_groups")
    if allowed_groups is None:
        return set()

    if not isinstance(allowed_groups, list) or any(
            not isinstance(group_id, int) or isinstance(group_id, bool) or group_id <= 0
            for group_id in allowed_groups
    ):
        raise HTTPException(status_code=502, detail="Sub2API 返回的用户分组格式无效")

    return set(allowed_groups)


def empty_accounts_payload(page: int, page_size: int) -> dict[str, Any]:
    return {
        "data": {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "pages": 1,
        },
    }


def filter_and_paginate_accounts(
        payload: dict[str, Any],
        group_ids: set[int],
        page: int,
        page_size: int,
) -> None:
    data = get_accounts_data(payload)
    accounts = [
        account
        for account in data["items"]
        if account.get("schedulable") is not False
        and group_ids.intersection(account.get("group_ids", []))
    ]
    total = len(accounts)
    start = (page - 1) * page_size

    data["items"] = accounts[start:start + page_size]
    data["total"] = total
    data["page"] = page
    data["page_size"] = page_size
    data["pages"] = max(1, (total + page_size - 1) // page_size)


async def enrich_accounts_with_usage(payload: dict[str, Any]) -> None:
    accounts = get_accounts_data(payload)["items"]
    if not accounts:
        return

    account_ids = [account.get("id") for account in accounts]

    async with Sub2ApiClient() as client:
        results = await asyncio.gather(*(
            client.get_account_usage(account_id)
            for account_id in account_ids
        ))

    for account, result in zip(accounts, results):
        usage = result.get("data")
        if not isinstance(usage, dict):
            raise HTTPException(status_code=502, detail="Sub2API 返回的账号用量格式无效")
        account["usage"] = usage


def get_accounts_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def sanitize_accounts_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = deepcopy(payload)
    data = safe_payload.get("data") if isinstance(safe_payload.get("data"), dict) else safe_payload
    items = data.get("items")

    if not isinstance(items, list):
        return safe_payload

    data["items"] = [sanitize_account(item) for item in items]
    return safe_payload


def sanitize_account(account: Any) -> Any:
    if not isinstance(account, dict):
        return account

    safe_account = {
        key: value
        for key, value in account.items()
        if key not in SENSITIVE_ACCOUNT_KEYS
    }

    mask_account_email(safe_account)
    return safe_account


def mask_account_email(account: dict[str, Any]) -> None:
    for key in ("name", "email"):
        value = account.get(key)
        if isinstance(value, str) and is_email(value):
            account[key] = mask_email(value)

    extra = account.get("extra")
    if isinstance(extra, dict):
        email = extra.get("email")
        if isinstance(email, str) and is_email(email):
            extra["email"] = mask_email(email)


def is_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value))


def mask_email(email: str) -> str:
    local, domain = email.split("@", 1)

    if len(local) <= 1:
        masked_local = "*"
    elif len(local) <= 3:
        masked_local = f"{local[0]}*"
    else:
        masked_local = f"{local[:3]}****{local[-2:]}"

    return f"{masked_local}@{domain}"
