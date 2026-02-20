"""Community room directory using a shared-owner-keypair DHT record.

Directory DHT record (DHTSchema.dflt(64)):
  subkey 0 : {"name": "public", "created": ts, "v": 1}
  subkeys 1-63: room entries or empty

Shared-owner model: The directory creator shares both the DHT key AND
the owner keypair.  Anyone with the keypair can write to any subkey.
This is intentionally public -- the keypair acts as a community write token.

Share string format: DIR:<base64(json({"k": dir_key, "p": dir_keypair}))>

Local persistence via TableDb("ascii_chat_directory", 1):
  Keys: dir_key, dir_keypair
"""

import base64
import hashlib
import json
import time

import veilid


# Characters used for 4-char short codes (unambiguous uppercase)
_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_short_code(room_key_str):
    """Derive a deterministic 4-char short code from a room key string."""
    h = hashlib.sha256(room_key_str.encode()).digest()
    code = []
    for i in range(4):
        code.append(_CODE_CHARS[h[i] % len(_CODE_CHARS)])
    return "".join(code)


class Directory:
    """Manages a community room directory on the Veilid DHT."""

    def __init__(self):
        self.dir_key = None          # TypedKey of the directory DHT record
        self.dir_keypair = None      # KeyPair for write access
        self._db = None              # TableDb handle

    @classmethod
    async def load(cls, api, rc):
        """Load saved directory from TableDb. Returns Directory or None."""
        self = cls()
        self._db = await api.open_table_db("ascii_chat_directory", 1)

        raw_key = await self._db.load(b"dir_key")
        raw_kp = await self._db.load(b"dir_keypair")

        if raw_key and raw_kp:
            self.dir_key = veilid.TypedKey(raw_key.decode())
            self.dir_keypair = veilid.KeyPair(raw_kp.decode())
            try:
                await rc.open_dht_record(self.dir_key, writer=self.dir_keypair)
            except Exception:
                return None
            return self
        return None

    @classmethod
    async def create(cls, api, rc):
        """Create a new directory DHT record."""
        self = cls()
        self._db = await api.open_table_db("ascii_chat_directory", 1)

        schema = veilid.DHTSchema.dflt(64)
        record = await rc.create_dht_record(veilid.CryptoKind.CRYPTO_KIND_VLD0, schema)
        self.dir_key = record.key
        self.dir_keypair = record.owner_key_pair()

        # Write directory header to subkey 0
        header = {"name": "public", "created": time.time(), "v": 1}
        await rc.set_dht_value(
            self.dir_key,
            veilid.ValueSubkey(0),
            json.dumps(header).encode(),
        )

        # Persist locally
        await self._db.store(b"dir_key", str(self.dir_key).encode())
        await self._db.store(b"dir_keypair", str(self.dir_keypair).encode())

        return self

    @classmethod
    async def join_from_share(cls, api, rc, share_string):
        """Join an existing directory from a share string.

        Accepts format: DIR:<base64_json>
        """
        self = cls()
        self._db = await api.open_table_db("ascii_chat_directory", 1)

        # Strip prefix
        payload = share_string
        if payload.upper().startswith("DIR:"):
            payload = payload[4:]

        info = json.loads(base64.b64decode(payload).decode())
        self.dir_key = veilid.TypedKey(info["k"])
        self.dir_keypair = veilid.KeyPair(info["p"])

        # Open with write access
        await rc.open_dht_record(self.dir_key, writer=self.dir_keypair)

        # Persist locally
        await self._db.store(b"dir_key", str(self.dir_key).encode())
        await self._db.store(b"dir_keypair", str(self.dir_keypair).encode())

        return self

    def get_share_string(self):
        """Return the share string for this directory."""
        info = {"k": str(self.dir_key), "p": str(self.dir_keypair)}
        encoded = base64.b64encode(json.dumps(info).encode()).decode()
        return f"DIR:{encoded}"

    async def register_room(self, rc, handle, room_key, title=""):
        """Claim an empty slot and register a room. Returns the short code."""
        room_str = str(room_key)
        short = _generate_short_code(room_str)

        entry = {
            "handle": handle,
            "room": room_str,
            "title": title,
            "short": short,
            "ts": time.time(),
        }
        data = json.dumps(entry).encode()

        # Find an empty slot (subkeys 1-63)
        for subkey in range(1, 64):
            vd = await rc.get_dht_value(
                self.dir_key, veilid.ValueSubkey(subkey), True
            )
            write_opts = veilid.types.SetDHTValueOptions(writer=self.dir_keypair)
            if vd is None or vd.data == b"" or vd.data == b"{}":
                await rc.set_dht_value(
                    self.dir_key,
                    veilid.ValueSubkey(subkey),
                    data,
                    options=write_opts,
                )
                return short

            # Check if the slot has an empty/cleared entry
            try:
                existing = json.loads(vd.data.decode())
                if not existing.get("room"):
                    await rc.set_dht_value(
                        self.dir_key,
                        veilid.ValueSubkey(subkey),
                        data,
                        options=write_opts,
                    )
                    return short
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Corrupted slot, overwrite it
                await rc.set_dht_value(
                    self.dir_key,
                    veilid.ValueSubkey(subkey),
                    data,
                    options=write_opts,
                )
                return short

        raise RuntimeError("Directory full (all 63 slots occupied)")

    async def unregister_room(self, rc, room_key):
        """Clear a room's slot in the directory."""
        room_str = str(room_key)
        for subkey in range(1, 64):
            try:
                vd = await rc.get_dht_value(
                    self.dir_key, veilid.ValueSubkey(subkey), True
                )
                if vd is None:
                    continue
                existing = json.loads(vd.data.decode())
                if existing.get("room") == room_str:
                    write_opts = veilid.types.SetDHTValueOptions(writer=self.dir_keypair)
                    await rc.set_dht_value(
                        self.dir_key,
                        veilid.ValueSubkey(subkey),
                        json.dumps({"room": None}).encode(),
                        options=write_opts,
                    )
                    return
            except Exception:
                continue

    async def list_rooms(self, rc):
        """Fetch all active room entries from the directory."""
        rooms = []
        for subkey in range(1, 64):
            try:
                vd = await rc.get_dht_value(
                    self.dir_key, veilid.ValueSubkey(subkey), True
                )
                if vd is None:
                    continue
                entry = json.loads(vd.data.decode())
                if entry.get("room"):
                    rooms.append(entry)
            except Exception:
                continue
        return rooms

    async def find_by_short_code(self, rc, code):
        """Look up a room entry by its 4-char short code."""
        code = code.upper()
        rooms = await self.list_rooms(rc)
        for entry in rooms:
            if entry.get("short", "").upper() == code:
                return entry
        return None
