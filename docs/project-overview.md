# Project Overview — ascii-veilid-chat

> Generated: 2026-02-16 | Scan Level: Deep

## Purpose

ascii-veilid-chat is a peer-to-peer ASCII video chat application that runs entirely in the terminal. It captures webcam video, converts it to colorized ASCII art in real time, and transmits it alongside text chat over the Veilid decentralized network. The result is a privacy-focused, serverless video chat experience that works in any terminal with 256-color support.

## Key Features

- **P2P ASCII Video Chat** — Real-time webcam-to-ASCII conversion with per-character color
- **Encrypted Communication** — All traffic encrypted via Veilid private routes (no central server)
- **Persistent Identity** — User profiles stored on the Veilid DHT with local TableDb backup
- **Room Directory** — Community room listings with shareable directory links and 4-char short codes
- **Terminal-Native** — Curses-based split-panel UI with video, chat, status, and input panels

## Tech Stack Summary

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| Networking | Veilid (decentralized P2P) |
| Video | OpenCV + NumPy → ASCII art |
| UI | curses (terminal) |
| Runtime | asyncio + threading |

## Architecture

- **Type:** CLI monolith
- **Pattern:** Event-driven with callback wiring
- **Modules:** 6 Python files at project root (+ entry point)
- **Entry Point:** `python main.py`
- **Persistence:** Veilid TableDb (local key-value store)
- **External Dependency:** Local `veilid-server` daemon

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Start veilid-server daemon (must be running)

# Host a room
python main.py

# Join a room (from another terminal/machine)
python main.py -j VLD0:xxxxxxxxx...
```

## Documentation Links

- [Architecture](./architecture.md) — Detailed module architecture, protocol specs, security model
- [Source Tree Analysis](./source-tree-analysis.md) — Annotated directory structure, data flow, dependencies
- [Development Guide](./development-guide.md) — Prerequisites, installation, CLI args, in-app commands
