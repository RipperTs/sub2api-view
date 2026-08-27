from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Query, Request

from app.services.sub2api_client import Sub2ApiClient


async def verify_page_user(
        request: Request,
        user_id: Annotated[int, Query(gt=0)],
        token: Annotated[str, Query(min_length=1)],
) -> dict[str, Any]:
    return await authenticate_user(request, user_id, token)


async def verify_api_user(
        request: Request,
        user_id: Annotated[int, Query(gt=0)],
        authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if authorization is None:
        raise HTTPException(status_code=401, detail="缺少用户认证信息")

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="用户认证信息格式无效")

    return await authenticate_user(request, user_id, token.strip())


async def verify_admin_user(
        user: Annotated[dict[str, Any], Depends(verify_api_user)],
) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")

    return user


async def authenticate_user(
        request: Request,
        user_id: int,
        token: str,
) -> dict[str, Any]:
    client_ip = request.client.host if request.client is not None else None
    payload = await Sub2ApiClient().get_current_user(
        token,
        client_ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    user = payload.get("data")

    if not isinstance(user, dict):
        raise HTTPException(status_code=502, detail="Sub2API 返回的用户信息格式无效")

    if user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="用户身份与访问参数不匹配")

    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="用户未启用")

    return user
