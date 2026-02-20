# ascii-veilid-chat

Peer-to-peer ASCII video chat that runs entirely in your terminal. Captures your webcam, converts it to colorized ASCII art in real time, and transmits it alongside text chat over the [Veilid](https://veilid.com) decentralized network. No central server, no IP exposure, fully end-to-end encrypted.

```
┌──────────────────────────────────────┬──────────────────┐
│  .,:;i1tfLCG08@@@80GCLft1i;:,.      │  CHAT            │
│  .:;i1tLCG08@@@@@@@@80GCLt1i;:.     │                  │
│  ,;i1tfLCG08@@@@@@@@@@80GCLft1      │  [14:22] alice:  │
│  :i1tfLCG08@@@@    @@@@80GCLft1     │    hey! can you  │
│  ;i1tfLCG08@@@      @@@80GCLft1     │    see me?       │
│  i1tfLCG08@@@        @@80GCLft1     │                  │
│  1tfLCG08@@@@        @@80GCLft1;    │  [14:22] bob:    │
│  tfLCG08@@@@@@@  @@@@@@80GCLft1i    │    loud and      │
│  fLCG08@@@@@@@@@@@@@@@@80GCLft1i    │    clear!        │
│  LCG08@@@@@@@@@@@@@@@@880GCLft1i    │                  │
├──────────────────────────────────────┴──────────────────┤
│ Room: VLD0:wYeZM-Xo0HvZkhD8ebBBWxGrGMMJEfF1IeNdBWrnh  │
├─────────────────────────────────────────────────────────┤
│ Connected | Room created                                │
├─────────────────────────────────────────────────────────┤
│ > _                                                     │
└─────────────────────────────────────────────────────────┘
```

## Features

- **Real-time ASCII video** — Webcam frames converted to colored ASCII art at up to 30fps
- **End-to-end encrypted** — All traffic routed through Veilid's encrypted private routes
- **Fully decentralized** — No central server, no accounts, no sign-up
- **Text chat** — Integrated chat alongside video
- **Persistent identity** — Display name and profile stored on the Veilid DHT
- **Room directory** — Community room listings with shareable links and 4-char short codes
- **Auto-bootstrap** — Automatically detects, builds, and starts `veilid-server` if needed
- **Cross-platform** — Works on Linux, macOS, and Windows

## Prerequisites

- **Python 3.12+**
- **Webcam** (any USB/built-in camera)
- **Terminal with 256-color support** (most modern terminals)
- **Git** and **Rust/Cargo** (only needed if `veilid-server` isn't already installed — the app will build it automatically)

Install Rust if needed: https://rustup.rs

## Installation

```bash
git clone https://github.com/scs-labrat/veilid-ascii-video-chat.git
cd veilid-ascii-video-chat

# Create a virtual environment (recommended)
python -m venv .chat
# Linux/macOS:
source .chat/bin/activate
# Windows:
.chat\Scripts\activate

pip install -r requirements.txt
```

### Installing the Veilid Python package

The app requires the Veilid Python package matching the server version (0.5.2). After the first run builds `veilid-server`, install the matching Python bindings from the cloned source:

```bash
pip install ./veilid/veilid-python
```

## Quick Start

### Host a room

```bash
python main.py
```

On first run, the app will:
1. Check if `veilid-server` is already running on port 5959
2. Look for an existing binary in your `PATH` or `./veilid/target/release/`
3. If not found, clone and build it from source (takes several minutes the first time)
4. Start the daemon and launch the chat UI

Once running, your camera fills the screen and a **room code** is displayed on its own line for easy copying:

```
Room: VLD0:wYeZM-Xo0HvZkhD8ebBBWxGrGMMJEfF1IeNdBWrnh-o
```

Share this code with someone to have them join.

### Join a room

```bash
python main.py -j VLD0:wYeZM-Xo0HvZkhD8ebBBWxGrGMMJEfF1IeNdBWrnh-o
```

Once connected, the screen splits: remote video on top (2/3), your camera on bottom (1/3), chat on the right.

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `-j`, `--join ROOM` | Join an existing room by code | (host mode) |
| `-c`, `--camera N` | Camera device index | `0` |
| `-W`, `--width N` | ASCII frame width in characters | `80` |
| `-H`, `--height N` | ASCII frame height in characters | `24` |
| `--fps N` | Outbound frame rate (1-30) | `10` |
| `--no-color` | Disable color output | color on |
| `--no-preview` | Hide local camera preview | preview on |
| `--handle NAME` | Set your display name | `anon` |
| `--dir SHARE` | Join a directory on startup | none |

## In-App Commands

### General
| Command | Description |
|---------|-------------|
| `/quit` | Exit the application |
| `/help` | Show all available commands |

### Display
| Command | Description |
|---------|-------------|
| `/color` | Toggle color rendering |
| `/preview` | Toggle local camera preview |
| `/fps <1-30>` | Set outbound frame rate |

### Camera
| Command | Description |
|---------|-------------|
| `/cam` | Show camera status |
| `/cam list` | List available cameras |
| `/cam <n>` | Switch to camera n |
| `/cam on\|off` | Enable/disable camera |

### Identity
| Command | Description |
|---------|-------------|
| `/handle <name>` | Set your display name |
| `/whoami` | Show your identity info |
| `/call <key>` | Look up a profile and join their room |

### Rooms & Directory
| Command | Description |
|---------|-------------|
| `/room` | Show current room code |
| `/join <code>` | Join by short code or full VLD0: key |
| `/publish [title]` | Publish room to directory |
| `/dir` | Show directory status |
| `/dir create` | Create a new directory |
| `/dir join <share>` | Join directory by share string |
| `/dir share` | Show directory share string |
| `/rooms` | List rooms in directory |

## Architecture

```
main.py          ─── Orchestrator: CLI parsing, callback wiring, main loop
├── bootstrap.py     Auto-detect, build, and start veilid-server
├── ascii_camera.py  Webcam capture → ASCII art conversion (background thread)
├── veilid_net.py    Veilid P2P transport, DHT rooms, message protocol
├── terminal_ui.py   Curses split-panel UI with dynamic layout
├── chat.py          Chat message model and history
├── identity.py      Persistent user identity on the Veilid DHT
└── directory.py     Community room directory (shared-owner DHT model)
```

### How it works

1. **Camera capture** runs in a background thread, converting webcam frames to ASCII art with per-character ANSI 256-color mapping
2. **Room creation** uses a Veilid DHT record with 2 subkeys — host writes their private route blob to subkey 0, guest writes theirs to subkey 1
3. **Once connected**, both peers exchange real-time data over Veilid `app_message` using zlib-compressed JSON packets
4. **All networking** is handled by the local `veilid-server` daemon — the app connects via JSON API on `localhost:5959`

### Protocol

Messages are zlib-compressed JSON with a type field:

| Type | Purpose | Payload |
|------|---------|---------|
| `f` | Video frame | `{"l": [...lines], "c": [[...colors]]}` |
| `m` | Chat message | `{"x": "text", "s": timestamp}` |
| `i` | Identity | `{"h": "handle", "pk": "profile_key"}` |
| `q` | Disconnect | (empty) |

## Security & Privacy

All security is provided by the Veilid network layer:

- **End-to-end encryption** via Veilid's private routes
- **No IP exposure** — traffic routes through the Veilid network
- **No central server** — fully peer-to-peer with DHT-based coordination
- **Cryptographic identity** — keypairs managed by Veilid, no passwords or tokens
- **Local-only persistence** — identity and directory data stored in Veilid's local TableDb

## Troubleshooting

### `veilid-server did not start within 15s`
Check `veilid-server.log` in the project root for daemon errors. Common causes:
- Port 5959 already in use by another process
- Firewall blocking outbound connections on port 5150

### `Could not open camera`
- Check that your webcam is connected and not in use by another app
- Try a different device index: `python main.py -c 1`
- List available cameras in-app with `/cam list`

### No color output
Your terminal may not support 256 colors. Try a modern terminal emulator (Windows Terminal, iTerm2, Kitty, Alacritty).

### `cargo not found` during build
Install Rust: https://rustup.rs — the app needs Cargo to build `veilid-server` from source.

## Running Tests

```bash
python -m pytest tests/
```

## License

See [LICENSE](LICENSE) for details.

## Documentation

Detailed technical documentation is available in the [`docs/`](docs/) directory:

- [Architecture](docs/architecture.md) — Module design, protocol specs, security model, concurrency
- [Development Guide](docs/development-guide.md) — Setup, development workflow, testing
- [Source Tree Analysis](docs/source-tree-analysis.md) — Annotated directory structure and data flow
