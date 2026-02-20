"""Veilid P2P networking for ASCII frame and chat transport.

Protocol
--------
Room creation uses a DHT record with 2 subkeys:
  subkey 0 : host's private-route blob  (JSON {"route": "<base64>"})
  subkey 1 : guest's private-route blob (same format)

Once both route blobs are exchanged, real-time data flows over
app_message using zlib-compressed JSON packets:
  {"t":"f", "l":[...], "c":[[...]]}   -- video frame (lines + colors)
  {"t":"m", "x":"text", "s":ts}       -- chat message
  {"t":"i", "h":"handle", "pk":"..."}  -- identity exchange
  {"t":"q"}                            -- quit / disconnect
"""

import asyncio
import base64
import json
import time
import zlib

import veilid


class VeilidNet:
    """Manages Veilid connection, DHT room, and message transport."""

    def __init__(self):
        self.api = None
        self.rc = None
        self.dht_key = None
        self.dht_owner_keypair = None
        self.my_route = None
        self.peer_route_id = None
        self.is_host = False
        self.connected = False
        self.running = False

        # Identity / social
        self.identity = None       # Identity instance (set from main.py)
        self.directory = None      # Directory instance (set from main.py)
        self.peer_handle = None    # Peer's display name

        # External callbacks
        self.on_frame = None   # (lines, colors) -> None
        self.on_chat = None    # (text, timestamp) -> None
        self.on_status = None  # (str) -> None

        self._msg_queue: asyncio.Queue = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Update callback wired into api_connector
    # ------------------------------------------------------------------
    async def _update_callback(self, update: veilid.VeilidUpdate):
        if update.kind == veilid.VeilidUpdateKind.APP_MESSAGE:
            await self._msg_queue.put(update.detail.message)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self):
        """Connect to the local veilid-server daemon."""
        self.running = True
        self._notify("Connecting to veilid-server...")
        self.api = await veilid.api_connector(self._update_callback)
        self.rc = await (await self.api.new_routing_context()).with_default_safety()

        # Create a private route so the peer can reach us
        self.my_route = await self.api.new_private_route()
        self._notify("Veilid ready")

    async def stop(self):
        self.running = False
        # Send quit to peer
        await self._send_raw({"t": "q"})

        # Clear room from identity profile
        if self.identity and self.rc:
            try:
                await self.identity.publish_room(self.rc, None)
            except Exception:
                pass

        # Unregister from directory
        if self.directory and self.dht_key and self.rc:
            try:
                await self.directory.unregister_room(self.rc, self.dht_key)
            except Exception:
                pass

        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

        if self.peer_route_id:
            try:
                await self.api.release_private_route(self.peer_route_id)
            except Exception:
                pass
        if self.my_route:
            try:
                await self.api.release_private_route(self.my_route.route_id)
            except Exception:
                pass
        if self.dht_key and self.rc:
            try:
                await self.rc.close_dht_record(self.dht_key)
            except Exception:
                pass
        if self.rc:
            try:
                await self.rc.release()
            except Exception:
                pass
        if self.api:
            try:
                await self.api.release()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Room management
    # ------------------------------------------------------------------
    async def create_room(self) -> str:
        """Create a DHT-backed room.  Returns the room code (record key)."""
        self.is_host = True

        record = await self.rc.create_dht_record(
            veilid.DHTSchema.dflt(2), veilid.CryptoKind.CRYPTO_KIND_VLD0
        )
        self.dht_key = record.key
        self.dht_owner_keypair = veilid.KeyPair(
            f"{record.owner}:{record.owner_secret}"
        )

        # Publish our route blob on subkey 0
        blob_b64 = base64.b64encode(self.my_route.blob).decode()
        await self.rc.set_dht_value(
            self.dht_key,
            veilid.ValueSubkey(0),
            json.dumps({"route": blob_b64}).encode(),
        )

        room_code = str(self.dht_key)
        self._notify(f"Room created  |  code: {room_code}")

        # Publish room to identity profile
        if self.identity:
            try:
                await self.identity.publish_room(self.rc, self.dht_key)
            except Exception:
                pass

        self._tasks.append(asyncio.create_task(self._poll_for_guest()))
        self._tasks.append(asyncio.create_task(self._receive_loop()))
        return room_code

    async def join_room(self, room_code: str):
        """Join an existing room by its code (record key)."""
        self.is_host = False
        self.dht_key = veilid.TypedKey(room_code)

        await self.rc.open_dht_record(self.dht_key)
        self._notify("Looking for host...")

        # Read host's route blob from subkey 0, retry a few times
        host_blob = None
        for attempt in range(15):
            vd = await self.rc.get_dht_value(
                self.dht_key, veilid.ValueSubkey(0), True
            )
            if vd is not None:
                info = json.loads(vd.data.decode())
                host_blob = base64.b64decode(info["route"])
                break
            await asyncio.sleep(1)

        if host_blob is None:
            raise RuntimeError("Room not found or host offline")

        self.peer_route_id = await self.api.import_remote_private_route(host_blob)

        # Publish our route blob on subkey 1
        blob_b64 = base64.b64encode(self.my_route.blob).decode()
        await self.rc.set_dht_value(
            self.dht_key,
            veilid.ValueSubkey(1),
            json.dumps({"route": blob_b64}).encode(),
        )

        self.connected = True
        self._notify("Connected to host!")
        self._tasks.append(asyncio.create_task(self._receive_loop()))
        await self._send_identity()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _poll_for_guest(self):
        """Host-side: poll subkey 1 until guest writes their route blob."""
        while self.running and not self.connected:
            try:
                vd = await self.rc.get_dht_value(
                    self.dht_key, veilid.ValueSubkey(1), True
                )
                if vd is not None:
                    info = json.loads(vd.data.decode())
                    guest_blob = base64.b64decode(info["route"])
                    self.peer_route_id = (
                        await self.api.import_remote_private_route(guest_blob)
                    )
                    self.connected = True
                    self._notify("Peer connected!")
                    await self._send_identity()
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _send_identity(self):
        """Send our identity info to the peer."""
        if not self.identity:
            return
        msg = {
            "t": "i",
            "h": self.identity.handle,
            "pk": str(self.identity.profile_key) if self.identity.profile_key else None,
        }
        await self._send_raw(msg)

    async def _receive_loop(self):
        """Drain incoming app_messages and dispatch to callbacks."""
        while self.running:
            try:
                raw = await asyncio.wait_for(self._msg_queue.get(), timeout=0.1)
                msg = json.loads(zlib.decompress(raw).decode())
                kind = msg.get("t")
                if kind == "f" and self.on_frame:
                    self.on_frame(msg["l"], msg["c"])
                elif kind == "m" and self.on_chat:
                    self.on_chat(msg["x"], msg.get("s"))
                elif kind == "i":
                    self.peer_handle = msg.get("h")
                    self._notify(f"Peer: {self.peer_handle or 'anon'}")
                elif kind == "q":
                    self._notify("Peer disconnected")
                    self.connected = False
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass

    async def _send_raw(self, obj: dict):
        if not self.connected or self.peer_route_id is None:
            return
        try:
            data = zlib.compress(json.dumps(obj, separators=(",", ":")).encode())
            await self.rc.app_message(self.peer_route_id, data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public send helpers
    # ------------------------------------------------------------------
    async def send_frame(self, lines: list[str], colors: list[list[int]]):
        await self._send_raw({"t": "f", "l": lines, "c": colors})

    async def send_chat(self, text: str):
        await self._send_raw({"t": "m", "x": text, "s": time.time()})

    # ------------------------------------------------------------------
    def _notify(self, text: str):
        if self.on_status:
            self.on_status(text)
