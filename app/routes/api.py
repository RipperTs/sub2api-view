from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.security import verify_access_key
from app.services.sub2api_client import Sub2ApiClient

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

    return {
        key: value
        for key, value in account.items()
        if key not in SENSITIVE_ACCOUNT_KEYS
    }
