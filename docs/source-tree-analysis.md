# Source Tree Analysis — ascii-veilid-chat

> Generated: 2026-02-16 | Scan Level: Deep

## Directory Structure

```
ascii-veilid-chat/
├── main.py              # [ENTRY POINT] CLI entry point + slash-command router
├── veilid_net.py        # P2P networking: DHT rooms, private routes, message transport
├── ascii_camera.py      # Webcam capture + ASCII art conversion (background thread)
├── terminal_ui.py       # Curses-based split-panel terminal UI
├── chat.py              # Chat message model + thread-safe history
├── identity.py          # Persistent user identity via Veilid DHT + local TableDb
├── directory.py         # Community room directory using shared-owner DHT records
├── requirements.txt     # Python dependency manifest (4 packages)
├── .chat/               # Python virtual environment (not tracked)
├── __pycache__/         # Python bytecode cache (not tracked)
├── docs/                # Generated documentation (this workflow's output)
├── _bmad/               # BMAD framework configuration (tooling)
└── _bmad-output/        # BMAD framework output (tooling)
```

## Critical Files

### Entry Point

- **`main.py`** — The single entry point for the entire application
  - CLI argument parsing via `argparse`
  - Async main loop: camera → network → UI render cycle at ~60fps
  - Slash-command handler for all in-app commands (`/quit`, `/color`, `/cam`, `/handle`, `/dir`, etc.)
  - Module instantiation and callback wiring

### Core Modules

- **`veilid_net.py`** — The networking backbone
  - Connects to local `veilid-server` daemon via `veilid.api_connector()`
  - Creates/joins DHT-backed rooms (2-subkey schema: host route + guest route)
  - zlib-compressed JSON message protocol: frames (`t:f`), chat (`t:m`), identity (`t:i`), quit (`t:q`)
  - Private route management for encrypted P2P communication

- **`ascii_camera.py`** — Camera capture pipeline
  - Background daemon thread for continuous webcam capture
  - OpenCV frame capture at 320x240 resolution
  - Real-time ASCII art conversion: brightness → character ramp (`" .,:;i1tfLCG08@"`)
  - Per-character ANSI 256-color mapping (BGR → RGB → ANSI)
  - Thread-safe frame buffer with `threading.Lock`

- **`terminal_ui.py`** — Terminal user interface
  - Curses-based split-panel layout:
    - Left: Remote video (top 2/3) + Local preview (bottom 1/3)
    - Right: Chat panel with word-wrapped messages
    - Bottom: Status bar + input line
  - 256-color support with graceful fallback
  - Keyboard input handling (arrows, backspace, delete, home/end, escape)
  - Dynamic layout recalculation on terminal resize

- **`chat.py`** — Chat message handling
  - `ChatMessage` data class with `__slots__` for memory efficiency
  - Thread-safe deque-based history (max 500 messages)
  - Send/receive with async callback dispatch
  - Message formatting with timestamps and handles

- **`identity.py`** — User identity management
  - DHT profile record (2-subkey schema): profile metadata + active room reference
  - Local persistence via Veilid TableDb (`ascii_chat_identity`)
  - Handle (display name) management with DHT synchronization
  - Profile lookup for calling other users

- **`directory.py`** — Community room directory
  - DHT record with 64 subkeys (header + 63 room slots)
  - Shared-owner model: keypair acts as community write token
  - Share string format: `DIR:<base64(json)>` for directory distribution
  - Deterministic 4-char short codes via SHA-256 hash

### Configuration

- **`requirements.txt`** — 4 dependencies: `veilid>=0.3.0`, `opencv-python>=4.8.0`, `numpy>=1.24.0`, `windows-curses>=2.3.0` (Windows only)

## Data Flow

```
┌─────────────┐   frames    ┌─────────────┐   compressed   ┌─────────────┐
│ AsciiCamera │ ──────────► │   main.py   │ ──────────────► │  VeilidNet  │
│  (thread)   │             │ (async loop)│                 │   (P2P)     │
└─────────────┘             └─────────────┘                 └─────────────┘
                                  │  ▲                           │  ▲
                          render  │  │ input                     │  │
                                  ▼  │                           │  │
                            ┌─────────────┐                     │  │
                            │ TerminalUI  │                     │  │
                            │  (curses)   │                     │  │
                            └─────────────┘                     │  │
                                  │  ▲                           │  │
                             chat │  │ display                   │  │
                                  ▼  │                           ▼  │
                            ┌─────────────┐               ┌──────────────┐
                            │    Chat     │               │   Identity   │
                            │  (history)  │               │  Directory   │
                            └─────────────┘               │   (DHT)     │
                                                          └──────────────┘
```

## Module Dependencies

| Module | Imports From |
|--------|-------------|
| `main.py` | `ascii_camera`, `chat`, `identity`, `directory`, `terminal_ui`, `veilid_net` |
| `veilid_net.py` | `veilid` (external) |
| `ascii_camera.py` | `cv2`, `numpy` (external) |
| `terminal_ui.py` | `curses` (stdlib) |
| `chat.py` | (stdlib only) |
| `identity.py` | `veilid` (external) |
| `directory.py` | `veilid` (external) |

All inter-module communication flows through `main.py` via callback wiring — no module imports another project module directly.
