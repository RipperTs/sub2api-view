import os
from typing import Annotated, Any

import jwt
from fastapi import Header, HTTPException, Query

from app.services.sub2api_client import Sub2ApiClient


async def verify_page_user(
        user_id: Annotated[int, Query(gt=0)],
        token: Annotated[str, Query(min_length=1)],
) -> dict[str, Any]:
    return await authenticate_user(user_id, token)


async def verify_api_user(
        user_id: Annotated[int, Query(gt=0)],
        authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    if authorization is None:
        raise HTTPException(status_code=401, detail="缺少用户认证信息")

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="用户认证信息格式无效")

    return await authenticate_user(user_id, token.strip())


async def authenticate_user(
        user_id: int,
        token: str,
) -> dict[str, Any]:
    token_user_id = decode_user_token(token)
    if token_user_id != user_id:
        raise HTTPException(status_code=403, detail="用户身份与访问参数不匹配")

    payload = await Sub2ApiClient().get_user(user_id)
    user = payload.get("data")

    if not isinstance(user, dict):
        raise HTTPException(status_code=502, detail="Sub2API 返回的用户信息格式无效")

    if user.get("id") != user_id:
        raise HTTPException(status_code=502, detail="Sub2API 返回的用户身份不匹配")

    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="用户未启用")

    return user


def decode_user_token(token: str) -> int:
    jwt_secret = os.getenv("SUB2API_JWT_SECRET", "")
    if not jwt_secret:
        raise HTTPException(status_code=500, detail="SUB2API_JWT_SECRET 未配置")

    try:
        claims = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256", "HS384", "HS512"],
            options={"require": ["exp", "nbf", "iat", "user_id", "token_version"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="用户 Token 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="用户 Token 无效") from exc

    token_user_id = claims.get("user_id")
    if not isinstance(token_user_id, int) or isinstance(token_user_id, bool) or token_user_id <= 0:
        raise HTTPException(status_code=401, detail="用户 Token 中的用户身份无效")

    return token_user_id
