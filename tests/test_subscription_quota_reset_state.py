import tempfile
import unittest
from pathlib import Path

from app.services.subscription_quota_reset_state import (
    SubscriptionQuotaResetStateStore,
)


class SubscriptionQuotaResetStateStoreTest(unittest.TestCase):
    def test_saves_and_loads_state_atomically(self) -> None:
        accounts = {
            "7": {
                "mode": "anchored",
                "reset_at": "2026-09-01T00:00:00+00:00",
                "last_boundary": "2026-08-25T00:00:00+00:00",
                "observed_at": "2026-08-28T00:00:00+00:00",
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "quota-reset-state.json"
            store = SubscriptionQuotaResetStateStore(state_path)

            store.save(accounts)

            self.assertEqual(store.load(), accounts)
            self.assertEqual(list(state_path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
