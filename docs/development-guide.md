# Development Guide — ascii-veilid-chat

> Generated: 2026-02-16 | Scan Level: Deep

## Prerequisites

| Requirement | Version | Notes |
|------------|---------|-------|
| Python | 3.10+ | Required for `list[str]`, `str \| None` union type syntax |
| veilid-server | 0.3.x+ | Local Veilid network daemon — must be running before app start |
| Webcam | Any | USB or built-in camera (optional — app works without it) |
| Terminal | 256-color | Minimum 60 columns x 12 rows; 256-color for video rendering |

### Platform-Specific

- **Windows:** Requires `windows-curses` package (auto-installed from requirements.txt)
- **Linux/macOS:** Uses built-in `curses` module (no extra dependency)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd ascii-veilid-chat

# Create and activate virtual environment
python -m venv .chat
# Windows:
.chat\Scripts\activate
# Linux/macOS:
source .chat/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Installing Veilid Server

The application requires a local `veilid-server` daemon running on the default port. See the [Veilid documentation](https://veilid.com) for installation instructions for your platform.

## Running the Application

### Host a Room

```bash
python main.py
```

This creates a new DHT-backed room and displays a room code (e.g., `VLD0:xxxxxxxxx...`) that others can use to join.

### Join a Room

```bash
python main.py -j VLD0:xxxxxxxxx...
```

### CLI Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `-j`, `--join ROOM` | — | Join an existing room by code |
| `-c`, `--camera N` | `0` | Camera device index |
| `-W`, `--width N` | `80` | ASCII frame width (characters) |
| `-H`, `--height N` | `24` | ASCII frame height (characters) |
| `--fps N` | `10` | Outbound frame rate (1-30) |
| `--no-color` | color on | Disable 256-color output |
| `--no-preview` | preview on | Hide local camera preview panel |
| `--handle NAME` | — | Set display name on startup |
| `--dir SHARE` | — | Join a directory by share string on startup |

### In-App Commands

| Command | Description |
|---------|-------------|
| `/quit` | Exit the application |
| `/color` | Toggle colour rendering |
| `/preview` | Toggle local camera preview |
| `/fps <n>` | Change send frame-rate (1-30) |
| `/cam list\|<n>\|off\|on` | Camera controls |
| `/room` | Show current room code |
| `/handle <name>` | Set your display name |
| `/whoami` | Show your identity info |
| `/call <profile_key>` | Look up a profile and join their room |
| `/dir create\|join\|share` | Directory management |
| `/rooms` | List rooms in directory |
| `/join <code>` | Join room by short code or full key |
| `/publish [title]` | Register current room in directory |
| `/help` | Show command help |

## Architecture Notes

### Main Event Loop

The application runs a single async event loop (`asyncio.run`) inside a `curses.wrapper`. The loop:

1. Captures local camera frame (from background thread)
2. Sends frame to peer via Veilid (rate-limited by FPS setting)
3. Handles keyboard input and slash commands
4. Renders the terminal UI
5. Yields with `asyncio.sleep(0.016)` (~60fps UI refresh)

### Veilid Dependency

The app connects to a **local** `veilid-server` process via `veilid.api_connector()`. It does NOT embed a Veilid node — the daemon must be running separately. All network operations (DHT reads/writes, private route creation, app messaging) go through this local daemon.

### Data Persistence

- **Identity:** Stored in Veilid's local TableDb (`ascii_chat_identity`) — survives across sessions
- **Directory:** Stored in Veilid's local TableDb (`ascii_chat_directory`) — survives across sessions
- **No file-based config** — all runtime settings are CLI arguments

## Testing

No test framework or test files are currently present in the project.

## Known Constraints

- Requires `veilid-server` daemon running locally
- DHT records may expire if the Veilid node goes offline for extended periods
- Directory limited to 63 room slots (DHT schema constraint)
- Single peer connection per room (host + guest only)
- Camera capture runs at 320x240 regardless of ASCII output dimensions
