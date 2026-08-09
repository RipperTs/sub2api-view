import asyncio
import re
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import verify_access_key
from app.services.sub2api_client import Sub2ApiClient
from app.services.subscription_quota_reset import SubscriptionQuotaResetService

router = APIRouter(prefix="/api", dependencies=[Depends(verify_access_key)])

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


@router.get("/accounts")
async def list_accounts(
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        platform: str | None = None,
        account_type: str | None = Query(default=None, alias="type"),
        status: str | None = None,
        group: str | None = None,
        search: str | None = None,
):
    params = {
        "page": page,
        "page_size": page_size,
        "platform": platform,
        "type": account_type,
        "status": status,
        "group": group,
        "search": search,
        "sort_order": "asc"
    }
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}

    payload = await Sub2ApiClient().list_accounts(clean_params)
    return sanitize_accounts_payload(payload)


@router.get("/accounts/{account_id}/usage")
async def get_account_usage(account_id: int):
    return await Sub2ApiClient().get_account_usage(account_id)


@router.post("/subscriptions/auto-reset")
async def auto_reset_subscription_quotas():
    if AUTO_RESET_LOCK.locked():
        raise HTTPException(status_code=409, detail="自动重置检测正在执行")

    async with AUTO_RESET_LOCK:
        async with Sub2ApiClient() as client:
            return await SubscriptionQuotaResetService(client).run()


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
