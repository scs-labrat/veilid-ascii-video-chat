# Architecture — ascii-veilid-chat

> Generated: 2026-02-16 | Scan Level: Deep

## Executive Summary

ascii-veilid-chat is a peer-to-peer ASCII video chat application that runs entirely in the terminal. It uses the Veilid decentralized network for encrypted, private communication between two peers. The application captures webcam video, converts it to colorized ASCII art in real time, and transmits it alongside text chat over Veilid's private route system. All state is persisted locally via Veilid's TableDb, with no external database or server required beyond the local Veilid daemon.

## Architecture Pattern

**Event-driven monolith with callback wiring**

The application follows a single-process, single-event-loop architecture where all modules are instantiated in `main.py` and connected via callback functions. There is no dependency injection framework, no message bus, and no service layer — communication flows through direct callback assignment.

```
main.py (orchestrator)
  ├── AsciiCamera  →  background thread, produces frames
  ├── VeilidNet    →  async P2P transport, produces/consumes messages
  ├── Chat         →  message model + history
  ├── Identity     →  DHT-based user profile
  ├── Directory    →  DHT-based room directory
  └── TerminalUI   →  curses rendering + input capture
```

### Key Design Decisions

1. **Callback wiring over imports:** No module imports another project module. All inter-module communication is wired in `main.py` via callbacks (`net.on_frame = ...`, `chat.on_send = ...`). This keeps modules decoupled and testable in isolation.

2. **Thread boundary at camera:** The camera capture runs in a daemon thread with a `threading.Lock`-protected frame buffer. The async main loop reads from this buffer. This isolates blocking OpenCV I/O from the async event loop.

3. **Single async event loop:** All network I/O, UI rendering, and input handling share one `asyncio` event loop inside `curses.wrapper`. The loop runs at ~60fps with `asyncio.sleep(0.016)`.

4. **Veilid as infrastructure:** The app delegates all networking, encryption, routing, and key management to the Veilid daemon. The application code handles only the protocol layer on top.

## Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| Language | Python | 3.10+ |
| P2P Network | Veilid | >=0.3.0 |
| Computer Vision | OpenCV (cv2) | >=4.8.0 |
| Numerical | NumPy | >=1.24.0 |
| Terminal UI | curses / windows-curses | stdlib / >=2.3.0 |
| Async Runtime | asyncio | stdlib |
| Compression | zlib | stdlib |

## Module Architecture

### main.py — Orchestrator (471 lines)

**Responsibilities:**
- CLI argument parsing (`argparse`)
- Module instantiation and callback wiring
- Main async event loop (camera → network → UI → yield)
- Slash-command routing (15 commands)

**Key function:** `run(stdscr, args)` — the async main loop that:
1. Instantiates all modules
2. Wires callbacks between them
3. Starts camera and Veilid connection
4. Runs the frame-input-render loop until `/quit`

### veilid_net.py — P2P Transport (275 lines)

**Responsibilities:**
- Veilid daemon connection via `api_connector()`
- DHT room creation/joining (2-subkey schema)
- Private route management (create, import, release)
- Message protocol: zlib-compressed JSON packets

**Protocol Types:**
| Type Code | Meaning | Payload |
|-----------|---------|---------|
| `f` | Video frame | `{"l": [lines], "c": [[colors]]}` |
| `m` | Chat message | `{"x": "text", "s": timestamp}` |
| `i` | Identity exchange | `{"h": "handle", "pk": "profile_key"}` |
| `q` | Quit/disconnect | (empty) |

**Room DHT Schema (2 subkeys):**
- Subkey 0: Host's private route blob (`{"route": "<base64>"}`)
- Subkey 1: Guest's private route blob (same format)

**Connection flow:**
1. Host creates DHT record, writes route blob to subkey 0
2. Guest opens DHT record, reads host blob from subkey 0, writes own blob to subkey 1
3. Host polls subkey 1 until guest blob appears
4. Both sides import each other's private routes → connected
5. Real-time data flows over `app_message` using imported routes

### ascii_camera.py — Video Pipeline (147 lines)

**Responsibilities:**
- Webcam capture via OpenCV (`VideoCapture`)
- Real-time ASCII art conversion
- Per-character ANSI 256-color mapping
- Thread-safe frame buffer

**Conversion pipeline:**
1. Capture frame at 320x240
2. Mirror horizontally (`cv2.flip`)
3. Resize to terminal dimensions
4. Convert to grayscale for brightness mapping
5. Map brightness to ASCII character ramp: `" .,:;i1tfLCG08@"` (15 chars, dark→light)
6. Map BGR pixels to ANSI 256-color codes: `16 + 36*R + 6*G + B` (where R,G,B ∈ [0,5])

### terminal_ui.py — Terminal Interface (339 lines)

**Responsibilities:**
- Curses-based split-panel layout rendering
- 256-color video display with graceful fallback
- Chat message display with word wrapping
- Keyboard input handling with cursor movement
- Dynamic layout recalculation on resize

**Layout:**
```
┌──────────────────────────┬──────────────┐
│      REMOTE VIDEO        │    CHAT      │
│      (top 2/3)           │              │
├──────────────────────────┤              │
│      LOCAL PREVIEW       │              │
│      (bottom 1/3)        │              │
├──────────────────────────┴──────────────┤
│ Status bar                              │
├─────────────────────────────────────────┤
│ > input line                            │
└─────────────────────────────────────────┘
```

### chat.py — Message Model (54 lines)

**Responsibilities:**
- `ChatMessage` data class with `__slots__` optimization
- Thread-safe deque-based history (max 500 messages)
- Async send with callback dispatch
- Message formatting: `[HH:MM] Handle: text`

### identity.py — User Identity (134 lines)

**Responsibilities:**
- Persistent identity via Veilid DHT + local TableDb
- Profile DHT record (2 subkeys): metadata + active room
- Handle management with DHT synchronization
- Profile lookup for `/call` command

**DHT Schema:**
- Subkey 0: `{"handle": "alice", "status": "available", "v": 1}`
- Subkey 1: `{"room": "VLD0:xxx...", "ts": 1234567890}` or `{"room": null}`

**Local Storage:** TableDb `ascii_chat_identity` with keys: `profile_key`, `owner_keypair`, `handle`

### directory.py — Room Directory (221 lines)

**Responsibilities:**
- Community room directory using shared-owner DHT model
- DHT record with 64 subkeys (1 header + 63 room slots)
- Share string distribution: `DIR:<base64(json({"k": key, "p": keypair}))>`
- Deterministic 4-char short codes from SHA-256

**Shared-owner model:** The directory creator generates a DHT keypair and distributes it via the share string. Anyone with the keypair can write to any subkey — the keypair acts as a community write token.

**Local Storage:** TableDb `ascii_chat_directory` with keys: `dir_key`, `dir_keypair`

## Security Architecture

All security is delegated to the Veilid network layer:

- **Encryption:** All P2P communication uses Veilid's encrypted private routes
- **Identity:** Cryptographic keypairs managed by Veilid (no passwords, no tokens)
- **Privacy:** No central server, no IP address exposure (Veilid routes through the network)
- **DHT Security:** Records are signed by owner keypairs; only authorized writers can modify

**Application-level security notes:**
- Directory keypair is intentionally shared (public write access by design)
- No authentication beyond Veilid's cryptographic identity
- No rate limiting on messages or frames
- zlib compression is not a security feature (just bandwidth optimization)

## Concurrency Model

```
┌─────────────────────────────────────────────┐
│              Main Process                    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │     asyncio Event Loop              │    │
│  │                                     │    │
│  │  ┌──────────┐  ┌──────────────┐    │    │
│  │  │ main loop│  │ _receive_loop│    │    │
│  │  │ (render) │  │ (Veilid msgs)│    │    │
│  │  └──────────┘  └──────────────┘    │    │
│  │                 ┌──────────────┐    │    │
│  │                 │_poll_for_guest│   │    │
│  │                 │  (host only)  │   │    │
│  │                 └──────────────┘    │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │     Camera Thread (daemon)          │    │
│  │     _capture_loop()                 │    │
│  │     Writes to shared frame buffer   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

- **Async tasks:** Main render loop, Veilid message receiver, guest poller (host only)
- **Thread boundary:** Camera capture thread ↔ async main loop via `threading.Lock`
- **No thread pool, no multiprocessing** — minimal concurrency model
