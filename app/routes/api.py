import asyncio
import re
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import verify_api_user
from app.services.sub2api_client import Sub2ApiClient

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
    group_ids = await list_user_subscription_group_ids(user["id"])
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


async def list_user_subscription_group_ids(user_id: int) -> set[int]:
    params = {
        "user_id": user_id,
        "status": "active",
        "sort_order": "asc",
    }
    page = 1
    group_ids: set[int] = set()

    async with Sub2ApiClient() as client:
        while True:
            payload = await client.list_subscriptions({
                **params,
                "page": page,
                "page_size": UPSTREAM_PAGE_SIZE,
            })
            data = get_subscriptions_data(payload)
            group_ids.update(
                subscription["group_id"]
                for subscription in data["items"]
                if isinstance(subscription, dict)
                and subscription.get("user_id") == user_id
                and subscription.get("status") == "active"
                and isinstance(subscription.get("group_id"), int)
                and not isinstance(subscription.get("group_id"), bool)
                and subscription["group_id"] > 0
            )

            if page >= data.get("pages", 1):
                break
            page += 1

    return group_ids


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


def get_subscriptions_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise HTTPException(status_code=502, detail="Sub2API 返回的订阅列表格式无效")
    return data


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
