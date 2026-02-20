# ascii-veilid-chat — Documentation Index

> Generated: 2026-02-16 | Mode: initial_scan | Scan Level: Deep

## Project Overview

- **Type:** CLI monolith
- **Primary Language:** Python 3.10+
- **Architecture:** Event-driven with callback wiring
- **Purpose:** P2P ASCII video chat over the Veilid decentralized network

## Quick Reference

- **Tech Stack:** Python 3 + Veilid + OpenCV + curses
- **Entry Point:** `main.py`
- **Architecture Pattern:** Single async event loop + background camera thread
- **Dependencies:** 4 packages (`veilid`, `opencv-python`, `numpy`, `windows-curses`)
- **External Requirement:** Local `veilid-server` daemon

## Generated Documentation

- [Project Overview](./project-overview.md) — Purpose, features, tech stack summary, quick start
- [Architecture](./architecture.md) — Module architecture, P2P protocol, security model, concurrency
- [Source Tree Analysis](./source-tree-analysis.md) — Annotated directory structure, data flow, module dependencies
- [Development Guide](./development-guide.md) — Prerequisites, installation, CLI args, in-app commands, constraints

## Getting Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Ensure veilid-server daemon is running

# 3. Host a room
python main.py

# 4. Join from another terminal/machine
python main.py -j VLD0:xxxxxxxxx...
```

## Key In-App Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/quit` | Exit |
| `/cam list` | List available cameras |
| `/handle <name>` | Set display name |
| `/dir create` | Create a room directory |
| `/publish` | List your room in directory |
| `/rooms` | Browse directory rooms |
| `/join <code>` | Join by 4-char short code |
