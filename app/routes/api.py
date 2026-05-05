from typing import Annotated

from fastapi import APIRouter, Query

from app.services.sub2api_client import Sub2ApiClient

router = APIRouter(prefix="/api")


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

    return await Sub2ApiClient().list_accounts(clean_params)
