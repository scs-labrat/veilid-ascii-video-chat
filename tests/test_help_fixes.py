"""Tests for help infrastructure fixes in main.py.

Fix 5: /help must list itself.
Fix 6: /help must be grouped by category.
Fix 7: /cam and /dir subcommands expanded in help.
Fix 8: Startup hint shown on launch.
Fix 9: All implemented commands must appear in /help.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeUI:
    """Minimal TerminalUI stand-in that captures chat output."""

    def __init__(self):
        self.chat_lines = []
        self.running = True
        self.status_text = ""
        self.color_enabled = True
        self.show_local = True

    def add_chat(self, text):
        self.chat_lines.append(text)

    def set_status(self, text):
        self.status_text = text


class TestHelpCommand(unittest.TestCase):
    """Tests for the /help slash command."""

    def _run_command(self, text):
        """Run a slash command and return the FakeUI with captured output."""
        from main import _handle_command

        ui = FakeUI()
        net = MagicMock()
        net.dht_key = None
        net.connected = False
        net.directory = None

        chat = MagicMock()
        camera = MagicMock()
        identity = MagicMock()
        identity.handle = "tester"
        args = MagicMock()

        result = _run(_handle_command(text, ui, net, chat, camera, identity, args))
        return result, ui

    def test_help_is_recognized_command(self):
        result, ui = self._run_command("/help")
        self.assertTrue(result)
        self.assertTrue(len(ui.chat_lines) > 0)

    def test_help_lists_itself(self):
        """Fix 5: /help must appear in its own output."""
        _, ui = self._run_command("/help")
        all_text = "\n".join(ui.chat_lines)
        self.assertIn("/help", all_text)

    def test_help_has_category_headers(self):
        """Fix 6: /help should have section headers for organization."""
        _, ui = self._run_command("/help")
        all_text = "\n".join(ui.chat_lines)
        self.assertIn("General", all_text)
        self.assertIn("Camera", all_text)
        self.assertIn("Identity", all_text)
        self.assertIn("Rooms", all_text)
        self.assertIn("Directory", all_text)

    def test_help_lists_cam_subcommands(self):
        """Fix 7: /cam subcommands should be expanded."""
        _, ui = self._run_command("/help")
        all_text = "\n".join(ui.chat_lines)
        self.assertIn("/cam list", all_text)
        # on|off may be on one line
        self.assertTrue(
            "/cam on" in all_text or "/cam on|off" in all_text,
            "/cam on or /cam on|off not found in help",
        )

    def test_help_lists_dir_subcommands(self):
        """Fix 7: /dir subcommands should be expanded."""
        _, ui = self._run_command("/help")
        all_text = "\n".join(ui.chat_lines)
        self.assertIn("/dir create", all_text)
        self.assertIn("/dir join", all_text)
        self.assertIn("/dir share", all_text)

    def test_all_implemented_commands_in_help(self):
        """Every slash command that _handle_command recognizes must be in /help."""
        _, ui = self._run_command("/help")
        all_text = "\n".join(ui.chat_lines)

        required_commands = [
            "/quit", "/help", "/color", "/preview", "/fps",
            "/cam", "/room", "/handle", "/whoami", "/call",
            "/dir", "/rooms", "/join", "/publish",
        ]
        for cmd in required_commands:
            self.assertIn(cmd, all_text, f"{cmd} missing from /help output")


class TestAllCommandsRecognized(unittest.TestCase):
    """Verify every command returns truthy (not 'Unknown command')."""

    def _run_command(self, text, **overrides):
        from main import _handle_command

        ui = FakeUI()
        net = MagicMock()
        net.dht_key = MagicMock()
        net.connected = False
        net.directory = None
        net.peer_handle = None
        net._send_identity = AsyncMock()

        chat = MagicMock()
        camera = MagicMock()
        camera.enabled = True
        camera.device = 0

        identity = MagicMock()
        identity.handle = "tester"
        identity.profile_key = "VLD0:testkey"
        identity.set_handle = AsyncMock()

        args = MagicMock()
        args.fps = 10

        for k, v in overrides.items():
            if k == "ui":
                ui = v
            elif k == "net":
                net = v
            elif k == "identity":
                identity = v

        result = _run(_handle_command(text, ui, net, chat, camera, identity, args))
        return result, ui

    def test_quit(self):
        result, _ = self._run_command("/quit")
        self.assertEqual(result, "quit")

    def test_color(self):
        result, _ = self._run_command("/color")
        self.assertTrue(result)

    def test_preview(self):
        result, _ = self._run_command("/preview")
        self.assertTrue(result)

    def test_fps_valid(self):
        result, _ = self._run_command("/fps 15")
        self.assertTrue(result)

    def test_fps_invalid(self):
        result, ui = self._run_command("/fps abc")
        self.assertTrue(result)
        self.assertIn("Usage", "\n".join(ui.chat_lines))

    def test_cam_no_arg(self):
        result, _ = self._run_command("/cam")
        self.assertTrue(result)

    def test_cam_list(self):
        result, _ = self._run_command("/cam list")
        self.assertTrue(result)

    def test_room(self):
        result, _ = self._run_command("/room")
        self.assertTrue(result)

    def test_handle_no_arg(self):
        result, ui = self._run_command("/handle")
        self.assertTrue(result)
        self.assertIn("Usage", "\n".join(ui.chat_lines))

    def test_handle_with_arg(self):
        result, _ = self._run_command("/handle NewName")
        self.assertTrue(result)

    def test_whoami(self):
        result, ui = self._run_command("/whoami")
        self.assertTrue(result)
        self.assertIn("tester", "\n".join(ui.chat_lines))

    def test_dir_no_arg(self):
        result, _ = self._run_command("/dir")
        self.assertTrue(result)

    def test_dir_share_no_directory(self):
        result, ui = self._run_command("/dir share")
        self.assertTrue(result)
        self.assertIn("No directory", "\n".join(ui.chat_lines))

    def test_rooms_no_directory(self):
        result, ui = self._run_command("/rooms")
        self.assertTrue(result)
        self.assertIn("No directory", "\n".join(ui.chat_lines))

    def test_join_no_arg(self):
        result, ui = self._run_command("/join")
        self.assertTrue(result)
        self.assertIn("Usage", "\n".join(ui.chat_lines))

    def test_publish_no_directory(self):
        result, ui = self._run_command("/publish")
        self.assertTrue(result)
        self.assertIn("No directory", "\n".join(ui.chat_lines))

    def test_unknown_command(self):
        result, ui = self._run_command("/xyzzy")
        self.assertTrue(result)
        self.assertIn("Unknown command", "\n".join(ui.chat_lines))

    def test_non_command_returns_false(self):
        result, _ = self._run_command("just a regular message")
        self.assertFalse(result)


class TestStartupHint(unittest.TestCase):
    """Fix 8: New users should see a '/help' hint on startup."""

    def test_startup_hint_present_in_run_setup(self):
        """The run() function should add a help hint to the UI early on."""
        # We can't easily test the full run() function since it needs curses,
        # but we can verify the hint message is in main.py's run() function.
        import inspect
        from main import run
        source = inspect.getsource(run)
        self.assertIn("/help", source)
        self.assertIn("add_chat", source)


if __name__ == "__main__":
    unittest.main()
