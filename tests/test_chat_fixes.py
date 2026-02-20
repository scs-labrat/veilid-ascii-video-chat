"""Tests for chat.py bug fixes.

Fix 3: send() must return the ChatMessage object so the caller doesn't
       need to fish it out of history (which is racy).
"""

import asyncio
import unittest


class TestChatSendReturnValue(unittest.TestCase):
    """Fix 3: chat.send() should return the sent ChatMessage."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_send_returns_message(self):
        from chat import Chat, ChatMessage
        c = Chat()
        msg = self._run(c.send("hello"))
        self.assertIsInstance(msg, ChatMessage)
        self.assertEqual(msg.text, "hello")
        self.assertEqual(msg.sender, "local")

    def test_send_empty_returns_none(self):
        from chat import Chat
        c = Chat()
        msg = self._run(c.send(""))
        self.assertIsNone(msg)

    def test_send_whitespace_returns_none(self):
        from chat import Chat
        c = Chat()
        msg = self._run(c.send("   "))
        self.assertIsNone(msg)

    def test_returned_message_is_same_object_in_history(self):
        """The returned message should be the exact object in history."""
        from chat import Chat
        c = Chat()
        msg = self._run(c.send("test"))
        history = c.get_history()
        self.assertIs(msg, history[-1])

    def test_handle_can_be_set_on_returned_message(self):
        """Caller should be able to set handle on the returned msg safely."""
        from chat import Chat
        c = Chat()
        msg = self._run(c.send("test"))
        msg.handle = "Alice"
        self.assertEqual(msg.handle, "Alice")
        # Should also be reflected in history since it's the same object
        self.assertEqual(c.get_history()[-1].handle, "Alice")

    def test_send_fires_callback(self):
        """send() should still invoke the on_send callback."""
        from chat import Chat
        sent_texts = []

        async def fake_send(text):
            sent_texts.append(text)

        c = Chat()
        c.on_send = fake_send
        self._run(c.send("hello callback"))
        self.assertEqual(sent_texts, ["hello callback"])

    def test_concurrent_messages_dont_cross(self):
        """Two rapid sends should return their own messages, not each other's."""
        from chat import Chat
        c = Chat()
        msg1 = self._run(c.send("first"))
        msg2 = self._run(c.send("second"))
        self.assertEqual(msg1.text, "first")
        self.assertEqual(msg2.text, "second")
        self.assertIsNot(msg1, msg2)


class TestChatReceive(unittest.TestCase):
    """Verify receive still works correctly (no regression)."""

    def test_receive_returns_message(self):
        from chat import Chat
        c = Chat()
        msg = c.receive("hi", handle="Bob")
        self.assertEqual(msg.text, "hi")
        self.assertEqual(msg.sender, "remote")
        self.assertEqual(msg.handle, "Bob")

    def test_format_message_with_handle(self):
        from chat import Chat
        c = Chat()
        msg = c.receive("hi", handle="Bob")
        formatted = Chat.format_message(msg)
        self.assertIn("Bob", formatted)
        self.assertIn("hi", formatted)

    def test_format_message_without_handle_shows_peer(self):
        from chat import Chat
        c = Chat()
        msg = c.receive("hi")
        formatted = Chat.format_message(msg)
        self.assertIn("Peer", formatted)


if __name__ == "__main__":
    unittest.main()
