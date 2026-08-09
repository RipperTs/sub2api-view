import unittest
from unittest.mock import AsyncMock, Mock

from app.services.sub2api_client import Sub2ApiClient


class Sub2ApiClientTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = Sub2ApiClient()
        self.client.base_url = "http://sub2api.test"
        self.client.admin_key = "admin-key"
        self.client.http_client = AsyncMock()
        response = Mock()
        response.json.return_value = {"code": 0, "data": {}}
        self.client.http_client.request.return_value = response

    async def test_forces_active_account_usage_refresh(self) -> None:
        await self.client.get_account_usage(42, force=True)

        self.client.http_client.request.assert_awaited_once_with(
            "GET",
            "/api/v1/admin/accounts/42/usage",
            headers={"Accept": "application/json", "x-api-key": "admin-key"},
            params={"source": "active", "force": "true"},
        )

    async def test_resets_all_subscription_quota_windows(self) -> None:
        await self.client.reset_subscription_quota(9)

        self.client.http_client.request.assert_awaited_once_with(
            "POST",
            "/api/v1/admin/subscriptions/9/reset-quota",
            headers={"Accept": "application/json", "x-api-key": "admin-key"},
            json={"daily": True, "weekly": True, "monthly": True},
        )


if __name__ == "__main__":
    unittest.main()
