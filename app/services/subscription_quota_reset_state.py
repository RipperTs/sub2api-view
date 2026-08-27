import json
import os
import tempfile
from pathlib import Path
from typing import Any

STATE_VERSION = 1


class SubscriptionQuotaResetStateError(RuntimeError):
    pass


class SubscriptionQuotaResetStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}

        try:
            with self.path.open(encoding="utf-8") as state_file:
                payload = json.load(state_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise SubscriptionQuotaResetStateError(
                f"订阅配额状态文件读取失败: {exc}"
            ) from exc

        if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
            raise SubscriptionQuotaResetStateError("订阅配额状态文件版本无效")

        accounts = payload.get("accounts")
        if not isinstance(accounts, dict):
            raise SubscriptionQuotaResetStateError("订阅配额状态文件格式无效")

        return {
            str(account_id): account_state
            for account_id, account_state in accounts.items()
            if isinstance(account_state, dict)
        }

    def save(self, accounts: dict[str, dict[str, Any]]) -> None:
        payload = {"version": STATE_VERSION, "accounts": accounts}

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_path = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                text=True,
            )
        except OSError as exc:
            raise SubscriptionQuotaResetStateError(
                f"订阅配额状态目录创建失败: {exc}"
            ) from exc

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as state_file:
                json.dump(payload, state_file, ensure_ascii=False, indent=2, sort_keys=True)
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, TypeError, ValueError) as exc:
            raise SubscriptionQuotaResetStateError(
                f"订阅配额状态文件保存失败: {exc}"
            ) from exc
        finally:
            try:
                Path(temporary_path).unlink(missing_ok=True)
            except OSError:
                pass
