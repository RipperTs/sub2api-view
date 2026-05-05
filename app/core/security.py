import os

from fastapi import HTTPException, Query


def verify_access_key(access_key: str = Query(default="")) -> None:
    view_access_key = os.getenv("VIEW_ACCESS_KEY", "")

    if not view_access_key:
        raise HTTPException(status_code=500, detail="VIEW_ACCESS_KEY 未配置")

    if access_key != view_access_key:
        raise HTTPException(status_code=403, detail="访问秘钥无效")
