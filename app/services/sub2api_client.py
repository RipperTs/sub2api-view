import os
from typing import Any

import httpx
from fastapi import HTTPException


class Sub2ApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("SUB2API_BASE_URL", "").rstrip("/")
        self.admin_key = os.getenv("SUB2API_ADMIN_KEY", "")
        self.http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "Sub2ApiClient":
        self._verify_config()
        self.http_client = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self.http_client is not None:
            await self.http_client.aclose()
            self.http_client = None

    async def list_accounts(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/admin/accounts", params=params)

    async def get_account_usage(
        self,
        account_id: int,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        params = {"source": "active", "force": "true"} if force else None
        return await self._request(
            "GET",
            f"/api/v1/admin/accounts/{account_id}/usage",
            params=params,
        )

    async def list_subscriptions(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/admin/subscriptions", params=params)

    async def reset_subscription_quota(self, subscription_id: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/v1/admin/subscriptions/{subscription_id}/reset-quota",
            json={"daily": True, "weekly": True, "monthly": True},
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self._verify_config()

        headers = {
            "Accept": "application/json",
            "x-api-key": self.admin_key,
        }

        try:
            if self.http_client is not None:
                response = await self.http_client.request(
                    method,
                    path,
                    headers=headers,
                    **kwargs,
                )
            else:
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

    def _verify_config(self) -> None:
        if not self.base_url or not self.admin_key:
            raise HTTPException(status_code=500, detail="Sub2API 环境配置缺失")
