import os
from typing import Any

import httpx
from fastapi import HTTPException


class Sub2ApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("SUB2API_BASE_URL", "").rstrip("/")
        self.admin_key = os.getenv("SUB2API_ADMIN_KEY", "")

    async def list_accounts(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/admin/accounts", params=params)

    async def get_account_usage(self, account_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/admin/accounts/{account_id}/usage")

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.base_url or not self.admin_key:
            raise HTTPException(status_code=500, detail="Sub2API 环境配置缺失")

        headers = {
            "Accept": "application/json",
            "x-api-key": self.admin_key,
        }

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = self._get_error_message(exc.response)
            raise HTTPException(status_code=exc.response.status_code, detail=message) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Sub2API 请求失败: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="Sub2API 返回了非 JSON 内容，请检查 SUB2API_BASE_URL 是否指向后端 API 服务",
            ) from exc

    @staticmethod
    def _get_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text or "Sub2API 返回异常"

        if isinstance(data, dict):
            return str(data.get("detail") or data.get("message") or data)

        return str(data)
