#!/usr/bin/env python3
"""ascii-veilid-chat  --  P2P ASCII video chat over Veilid.

Usage
-----
  Host a room   :  python main.py
  Join a room   :  python main.py -j VLD0:xxxxxxxxx…

In-app commands
---------------
  /quit          Exit the application
  /color         Toggle colour rendering
  /preview       Toggle local camera preview
  /fps <n>       Change send frame-rate
  /cam           Camera controls (list/switch/on/off)
  /mic on|off    Enable / disable microphone
  /speaker on|off  Enable / disable speaker
  /devices       List audio input devices
  /handle <name> Set your display name
  /whoami        Show your identity info
  /call <key>    Look up a profile and join their room
  /dir           Directory management
  /rooms         List rooms in directory
  /join <code>   Join room by short code or full key
  /publish       Register current room in directory
"""

import argparse
import asyncio
import curses
import sys

from ascii_camera import AsciiCamera
from audio_io import AudioCapture, AudioPlayback
from bootstrap import ensure_veilid_server, stop_veilid_server
from chat import Chat
from identity import Identity
from directory import Directory
from terminal_ui import TerminalUI
from veilid_net import VeilidNet


# ──────────────────────────────────────────────────────────────────────
# Main async loop (runs inside curses.wrapper)
# ──────────────────────────────────────────────────────────────────────
async def run(stdscr, args):
    # --- Instantiate modules ---
    camera = AsciiCamera(args.width, args.height, device=args.camera)
    mic = AudioCapture()
    speaker = AudioPlayback()
    net = VeilidNet()
    chat = Chat()
    ui = TerminalUI(stdscr, color=args.color, show_local=not args.no_preview)

    room_code = ""
    identity = None
    mic_active = False  # mic starts off; user enables with /mic on

    ui.add_chat("[sys] Type /help for a list of commands")

    # --- Wire callbacks ---
    def on_remote_frame(lines, colors):
        ui.set_remote_frame(lines, colors)

    def on_remote_chat(text, timestamp):
        handle = net.peer_handle
        msg = chat.receive(text, timestamp, handle=handle)
        ui.add_chat(Chat.format_message(msg))

    def on_remote_audio(seq, pcm_bytes):
        speaker.enqueue(pcm_bytes)

    def on_status(text):
        ui.set_status(text)

    async def on_chat_send(text):
        await net.send_chat(text)

    net.on_frame = on_remote_frame
    net.on_chat = on_remote_chat
    net.on_audio = on_remote_audio
    net.on_status = on_status
    chat.on_send = on_chat_send

    # --- Start audio playback (always ready to receive) ---
    speaker_ok = False
    try:
        speaker.start()
        speaker_ok = True
    except Exception as exc:
        ui.add_chat(f"[sys] Speaker init failed: {exc}")

    # --- Start camera ---
    camera_ok = False
    try:
        camera.start()
        camera_ok = True
    except RuntimeError as exc:
        ui.set_status(f"Camera: {exc}")

    # --- Connect to Veilid ---
    veilid_ok = False
    try:
        await net.start()
        veilid_ok = True

        # --- Initialize identity ---
        try:
            identity = await Identity.load_or_create(
                net.api, net.rc, default_handle=args.handle
            )
            net.identity = identity
            if args.handle and identity.handle != args.handle:
                await identity.set_handle(net.rc, args.handle)
            ui.add_chat(f"[sys] Identity: {identity.handle}")
        except Exception as exc:
            ui.add_chat(f"[sys] Identity error: {exc}")

        # --- Initialize directory ---
        try:
            loaded = await Directory.load(net.api, net.rc)
            if loaded:
                net.directory = loaded
                ui.add_chat("[sys] Directory loaded")
            elif args.dir:
                net.directory = await Directory.join_from_share(
                    net.api, net.rc, args.dir
                )
                ui.add_chat("[sys] Joined directory")
        except Exception as exc:
            ui.add_chat(f"[sys] Directory: {exc}")

        if args.join:
            await net.join_room(args.join)
        else:
            room_code = await net.create_room()
            ui.room_code = room_code
    except Exception as exc:
        ui.set_status(f"Veilid: {exc}")

    # --- Main loop ---
    last_frame_time = 0.0

    try:
        while ui.running:
            now = asyncio.get_event_loop().time()

            # Local camera → UI + network
            if camera_ok and camera.enabled:
                local_lines, local_colors = camera.get_frame()
                if local_lines is not None:
                    ui.set_local_frame(local_lines, local_colors)
                    frame_interval = 1.0 / max(1, args.fps)
                    if (
                        veilid_ok
                        and net.connected
                        and now - last_frame_time >= frame_interval
                    ):
                        await net.send_frame(local_lines, local_colors)
                        last_frame_time = now

            # Local mic → network
            if mic_active and veilid_ok and net.connected:
                seq, pcm = mic.get_chunk()
                if pcm is not None:
                    await net.send_audio(seq, pcm)

            # Input
            msg = ui.handle_input()
            if msg:
                handled = await _handle_command(
                    msg, ui, net, chat, camera, mic, speaker,
                    identity, args, mic_active,
                )
                if handled == "quit":
                    break
                if handled == "mic_on":
                    if not mic_active:
                        try:
                            mic.start()
                            mic_active = True
                            ui.mic_on = True
                            ui.add_chat("[sys] Mic ON")
                        except Exception as e:
                            ui.add_chat(f"[sys] Mic error: {e}")
                    else:
                        ui.add_chat("[sys] Mic already on")
                elif handled == "mic_off":
                    if mic_active:
                        mic.stop()
                        mic_active = False
                        ui.mic_on = False
                        ui.add_chat("[sys] Mic OFF")
                    else:
                        ui.add_chat("[sys] Mic already off")
                elif handled == "speaker_on":
                    speaker.enabled = True
                    ui.speaker_on = True
                    ui.add_chat("[sys] Speaker ON")
                elif handled == "speaker_off":
                    speaker.enabled = False
                    ui.speaker_on = False
                    ui.add_chat("[sys] Speaker OFF")
                elif not handled:
                    # Tag outgoing messages with our handle
                    handle = identity.handle if identity else None
                    sent_msg = await chat.send(msg)
                    if sent_msg:
                        sent_msg.handle = handle
                        ui.add_chat(Chat.format_message(sent_msg))

            # Render
            ui.render()

            # Yield
            await asyncio.sleep(0.016)
    finally:
        if mic_active:
            mic.stop()
        speaker.stop()
        camera.stop()
        if veilid_ok:
            await net.stop()


# ──────────────────────────────────────────────────────────────────────
# Slash-command handler
# ──────────────────────────────────────────────────────────────────────
async def _handle_command(text, ui, net, chat, camera, mic, speaker,
                          identity, args, mic_active):
    """Return truthy if the text was a command, 'quit' to exit."""
    if not text.startswith("/"):
        return False

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) == 2 else ""

    if cmd == "/quit":
        return "quit"

    if cmd == "/color":
        ui.color_enabled = not ui.color_enabled
        ui.add_chat(f"[sys] Colour {'on' if ui.color_enabled else 'off'}")
        return True

    if cmd == "/preview":
        ui.show_local = not ui.show_local
        ui.add_chat(f"[sys] Preview {'on' if ui.show_local else 'off'}")
        return True

    if cmd == "/fps":
        if arg.isdigit():
            args.fps = max(1, min(30, int(arg)))
            ui.add_chat(f"[sys] FPS set to {args.fps}")
        else:
            ui.add_chat("[sys] Usage: /fps <1-30>")
        return True

    if cmd == "/cam":
        sub = arg.lower()
        if sub == "list":
            cams = AsciiCamera.enumerate_cameras()
            if cams:
                ui.add_chat(f"[sys] Available cameras: {cams}")
            else:
                ui.add_chat("[sys] No cameras found")
        elif sub == "off":
            camera.disable()
            ui.set_local_frame(None, None)
            ui.add_chat("[sys] Camera disabled")
        elif sub == "on":
            try:
                camera.enable()
                ui.add_chat("[sys] Camera enabled")
            except RuntimeError as e:
                ui.add_chat(f"[sys] Camera error: {e}")
        elif sub.isdigit():
            idx = int(sub)
            try:
                camera.switch_camera(idx)
                ui.add_chat(f"[sys] Switched to camera {idx}")
            except RuntimeError as e:
                ui.add_chat(f"[sys] Camera error: {e}")
        else:
            state = "on" if camera.enabled else "off"
            ui.add_chat(f"[sys] Camera {camera.device} ({state})")
            ui.add_chat("[sys] /cam list|<n>|off|on")
        return True

    if cmd == "/room":
        code = str(net.dht_key) if net.dht_key else "(no room)"
        ui.add_chat(f"[sys] Room: {code}")
        return True

    # ── Identity commands ──

    if cmd == "/handle":
        if not arg:
            ui.add_chat("[sys] Usage: /handle <name>")
            return True
        if not identity:
            ui.add_chat("[sys] Identity not initialized")
            return True
        try:
            await identity.set_handle(net.rc, arg)
            ui.add_chat(f"[sys] Handle set to: {arg}")
            # Re-send identity to peer
            await net._send_identity()
        except Exception as e:
            ui.add_chat(f"[sys] Error: {e}")
        return True

    if cmd == "/whoami":
        if identity:
            ui.add_chat(f"[sys] Handle: {identity.handle}")
            ui.add_chat(f"[sys] Profile: {identity.profile_key}")
        else:
            ui.add_chat("[sys] Identity not initialized")
        return True

    if cmd == "/call":
        if not net.rc:
            ui.add_chat("[sys] Veilid not connected")
            return True
        if not arg:
            ui.add_chat("[sys] Usage: /call <profile_key>")
            return True
        ui.add_chat("[sys] Looking up profile...")
        result = await Identity.lookup_profile(net.rc, arg)
        if not result:
            ui.add_chat("[sys] Profile not found")
            return True
        handle, status, room = result
        ui.add_chat(f"[sys] {handle} ({status})")
        if room:
            ui.add_chat(f"[sys] Joining {handle}'s room...")
            try:
                await net.join_room(room)
            except Exception as e:
                ui.add_chat(f"[sys] Join failed: {e}")
        else:
            ui.add_chat("[sys] No active room")
        return True

    # ── Directory commands ──

    if cmd == "/dir":
        if not net.api or not net.rc:
            ui.add_chat("[sys] Veilid not connected")
            return True

        sub_parts = arg.split(maxsplit=1)
        sub = sub_parts[0].lower() if sub_parts else ""

        if sub == "create":
            try:
                net.directory = await Directory.create(net.api, net.rc)
                share = net.directory.get_share_string()
                ui.add_chat("[sys] Directory created!")
                ui.add_chat(f"[sys] Share: {share}")
            except Exception as e:
                ui.add_chat(f"[sys] Error: {e}")
            return True

        if sub == "join":
            share_str = sub_parts[1].strip() if len(sub_parts) > 1 else ""
            if not share_str:
                ui.add_chat("[sys] Usage: /dir join <share_string>")
                return True
            try:
                net.directory = await Directory.join_from_share(
                    net.api, net.rc, share_str
                )
                ui.add_chat("[sys] Joined directory!")
            except Exception as e:
                ui.add_chat(f"[sys] Error: {e}")
            return True

        if sub == "share":
            if net.directory:
                ui.add_chat(f"[sys] {net.directory.get_share_string()}")
            else:
                ui.add_chat("[sys] No directory configured")
            return True

        # Default: show status
        if net.directory:
            ui.add_chat(f"[sys] Directory: {net.directory.dir_key}")
        else:
            ui.add_chat("[sys] No directory")
        ui.add_chat("[sys] /dir create|join|share")
        return True

    if cmd == "/rooms":
        if not net.directory:
            ui.add_chat("[sys] No directory. Use /dir create or /dir join")
            return True
        try:
            rooms = await net.directory.list_rooms(net.rc)
            if not rooms:
                ui.add_chat("[sys] No rooms listed")
            else:
                for r in rooms:
                    ui.add_chat(
                        f"[sys] [{r['short']}] {r['handle']}: "
                        f"{r.get('title', '(untitled)')}"
                    )
        except Exception as e:
            ui.add_chat(f"[sys] Error: {e}")
        return True

    if cmd == "/join":
        if not arg:
            ui.add_chat("[sys] Usage: /join <code|VLD0:key>")
            return True
        room_key = None
        if arg.startswith("VLD0:"):
            room_key = arg
        elif net.directory:
            try:
                entry = await net.directory.find_by_short_code(net.rc, arg.upper())
                if entry:
                    room_key = entry["room"]
                    ui.add_chat(f"[sys] Found: {entry['handle']}'s room")
                else:
                    ui.add_chat(f"[sys] Code '{arg}' not found")
                    return True
            except Exception as e:
                ui.add_chat(f"[sys] Error: {e}")
                return True
        else:
            ui.add_chat("[sys] No directory. Use full VLD0: key")
            return True
        if room_key:
            try:
                await net.join_room(room_key)
            except Exception as e:
                ui.add_chat(f"[sys] Join failed: {e}")
        return True

    if cmd == "/publish":
        if not net.directory:
            ui.add_chat("[sys] No directory. Use /dir create or /dir join")
            return True
        if not net.dht_key:
            ui.add_chat("[sys] No active room to publish")
            return True
        handle = identity.handle if identity else "anon"
        title = arg if arg else ""
        try:
            code = await net.directory.register_room(
                net.rc, handle, net.dht_key, title
            )
            ui.add_chat(f"[sys] Published! Code: {code}")
        except Exception as e:
            ui.add_chat(f"[sys] Error: {e}")
        return True

    # ── Audio commands ──

    if cmd == "/mic":
        sub = arg.lower()
        if sub == "on":
            return "mic_on"
        elif sub == "off":
            return "mic_off"
        else:
            state = "ON" if mic_active else "OFF"
            ui.add_chat(f"[sys] Mic is {state}")
            ui.add_chat("[sys] /mic on|off")
        return True

    if cmd == "/speaker":
        sub = arg.lower()
        if sub == "on":
            return "speaker_on"
        elif sub == "off":
            return "speaker_off"
        else:
            state = "ON" if speaker.enabled else "OFF"
            ui.add_chat(f"[sys] Speaker is {state}")
            ui.add_chat("[sys] /speaker on|off")
        return True

    if cmd == "/devices":
        try:
            devs = AudioCapture.list_devices()
            if devs:
                ui.add_chat("[sys] Audio input devices:")
                for d in devs:
                    ui.add_chat(f"[sys]   {d}")
            else:
                ui.add_chat("[sys] No audio input devices found")
        except Exception as e:
            ui.add_chat(f"[sys] Error: {e}")
        return True

    if cmd == "/banner":
        if not arg:
            ui.add_chat("[sys] Usage: /banner <text>")
            return True
        # Strip surrounding quotes if present
        text = arg.strip("\"'")
        ui.start_banner(text)
        return True

    if cmd == "/help":
        sections = (
            ("── General ──", (
                "/quit          exit the application",
                "/help          show this help",
            )),
            ("── Display ──", (
                "/color         toggle colour rendering",
                "/preview       toggle local camera preview",
                "/fps <1-30>    set outbound frame-rate",
                "/banner <text> show block-letter overlay",
            )),
            ("── Audio ──", (
                "/mic on|off    enable / disable microphone",
                "/speaker on|off  enable / disable speaker",
                "/devices       list audio input devices",
            )),
            ("── Camera ──", (
                "/cam           show camera status",
                "/cam list      list available cameras",
                "/cam <n>       switch to camera n",
                "/cam on|off    enable / disable camera",
            )),
            ("── Identity ──", (
                "/handle <name> set your display name",
                "/whoami        show your identity info",
                "/call <key>    look up profile & join room",
            )),
            ("── Rooms ──", (
                "/room          show current room code",
                "/join <code>   join by short code or VLD0: key",
                "/publish [t]   publish room to directory",
            )),
            ("── Directory ──", (
                "/dir           show directory status",
                "/dir create    create a new directory",
                "/dir join <s>  join directory by share string",
                "/dir share     show share string",
                "/rooms         list rooms in directory",
            )),
        )
        for header, lines in sections:
            ui.add_chat(f"[sys] {header}")
            for line in lines:
                ui.add_chat(f"[sys]   {line}")
        return True

    ui.add_chat(f"[sys] Unknown command: {cmd}")
    return True


# ──────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="ascii-veilid-chat",
        description="P2P ASCII video chat over the Veilid network",
    )
    parser.add_argument(
        "-j", "--join", metavar="ROOM",
        help="Join an existing room (paste the room code)",
    )
    parser.add_argument(
        "-c", "--camera", type=int, default=0,
        help="Camera device index (default: 0)",
    )
    parser.add_argument(
        "-W", "--width", type=int, default=80,
        help="ASCII frame width in characters (default: 80)",
    )
    parser.add_argument(
        "-H", "--height", type=int, default=24,
        help="ASCII frame height in characters (default: 24)",
    )
    parser.add_argument(
        "--fps", type=int, default=10,
        help="Outbound frame rate (default: 10)",
    )
    parser.add_argument(
        "--no-color", dest="color", action="store_false",
        help="Disable colour output",
    )
    parser.add_argument(
        "--no-preview", action="store_true",
        help="Hide local camera preview panel",
    )
    parser.add_argument(
        "--handle", type=str, default=None,
        help="Set your display name",
    )
    parser.add_argument(
        "--dir", type=str, default=None, metavar="SHARE",
        help="Join a directory by share string on startup",
    )
    args = parser.parse_args()

    # Ensure veilid-server is running before entering curses mode
    # so build/startup output is visible in the terminal.
    veilid_proc, we_started = ensure_veilid_server()

    def wrapper(stdscr):
        asyncio.run(run(stdscr, args))

    try:
        curses.wrapper(wrapper)
    except KeyboardInterrupt:
        pass
    finally:
        stop_veilid_server(veilid_proc, we_started)


if __name__ == "__main__":
    main()
