"""Tests for identity.py bug fixes.

Fix 4: When a DHT record can't be reopened, stale keys must be cleared
       from TableDb before creating a fresh identity.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeTableDb:
    """In-memory fake of Veilid's TableDb for testing."""

    def __init__(self):
        self._store = {}

    async def load(self, key):
        return self._store.get(key)

    async def store(self, key, value):
        self._store[key] = value


class TestIdentityStaleDataCleanup(unittest.TestCase):
    """Fix 4: expired DHT record should clear stale TableDb data."""

    @patch("identity.veilid")
    def test_expired_record_clears_tabledb_before_recreate(self, mock_veilid):
        """When open_dht_record fails, old keys should be wiped first."""

        db = FakeTableDb()

        # Pre-populate with stale data
        _run(db.store(b"profile_key", b"VLD0:oldkey"))
        _run(db.store(b"owner_keypair", b"oldpub:oldsecret"))
        _run(db.store(b"handle", b"OldName"))

        # Mock API
        mock_api = AsyncMock()
        mock_api.open_table_db = AsyncMock(return_value=db)

        # Mock routing context
        mock_rc = AsyncMock()
        # open_dht_record should fail (simulating expired record)
        mock_rc.open_dht_record = AsyncMock(side_effect=Exception("record expired"))
        # create_dht_record should succeed for the fresh identity
        mock_new_record = MagicMock()
        mock_new_record.key = "VLD0:newkey"
        mock_new_record.owner_key_pair.return_value = "newpub:newsecret"
        mock_rc.create_dht_record = AsyncMock(return_value=mock_new_record)
        mock_rc.set_dht_value = AsyncMock()

        # Mock veilid types
        mock_veilid.TypedKey = lambda x: x
        mock_veilid.KeyPair = lambda x: x
        mock_veilid.DHTSchema.dflt = lambda n: f"schema({n})"
        mock_veilid.ValueSubkey = lambda n: n

        from identity import Identity
        identity = _run(Identity.load_or_create(mock_api, mock_rc, default_handle="Fresh"))

        # After the fix, the old stale data should have been cleared
        # and then overwritten with new data
        new_key = _run(db.load(b"profile_key"))
        new_kp = _run(db.load(b"owner_keypair"))
        new_handle = _run(db.load(b"handle"))

        self.assertEqual(new_key, b"VLD0:newkey")
        self.assertEqual(new_kp, b"newpub:newsecret")
        self.assertEqual(new_handle, b"Fresh")
        self.assertEqual(identity.handle, "Fresh")

    @patch("identity.veilid")
    def test_valid_record_reuses_existing_identity(self, mock_veilid):
        """When open_dht_record succeeds, existing identity should be reused."""

        db = FakeTableDb()
        _run(db.store(b"profile_key", b"VLD0:goodkey"))
        _run(db.store(b"owner_keypair", b"pub:secret"))
        _run(db.store(b"handle", b"ExistingUser"))

        mock_api = AsyncMock()
        mock_api.open_table_db = AsyncMock(return_value=db)

        mock_rc = AsyncMock()
        # open_dht_record succeeds this time
        mock_rc.open_dht_record = AsyncMock()

        mock_veilid.TypedKey = lambda x: x
        mock_veilid.KeyPair = lambda x: x

        from identity import Identity
        identity = _run(Identity.load_or_create(mock_api, mock_rc))

        self.assertEqual(identity.handle, "ExistingUser")
        self.assertEqual(identity.profile_key, "VLD0:goodkey")
        # create_dht_record should NOT have been called
        mock_rc.create_dht_record.assert_not_called()

    @patch("identity.veilid")
    def test_no_existing_data_creates_new(self, mock_veilid):
        """When TableDb has no data, a new identity is created."""

        db = FakeTableDb()

        mock_api = AsyncMock()
        mock_api.open_table_db = AsyncMock(return_value=db)

        mock_rc = AsyncMock()
        mock_new_record = MagicMock()
        mock_new_record.key = "VLD0:brandnew"
        mock_new_record.owner_key_pair.return_value = "newpub:newsec"
        mock_rc.create_dht_record = AsyncMock(return_value=mock_new_record)
        mock_rc.set_dht_value = AsyncMock()

        mock_veilid.TypedKey = lambda x: x
        mock_veilid.KeyPair = lambda x: x
        mock_veilid.DHTSchema.dflt = lambda n: f"schema({n})"
        mock_veilid.ValueSubkey = lambda n: n

        from identity import Identity
        identity = _run(Identity.load_or_create(mock_api, mock_rc, default_handle="NewUser"))

        self.assertEqual(identity.handle, "NewUser")
        self.assertEqual(identity.profile_key, "VLD0:brandnew")


if __name__ == "__main__":
    unittest.main()
