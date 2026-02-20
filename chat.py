"""Chat message handling with thread-safe history."""

import collections
import time


class ChatMessage:
    __slots__ = ("text", "sender", "timestamp", "handle")

    def __init__(self, text, sender, timestamp=None, handle=None):
        self.text = text
        self.sender = sender          # "local" or "remote"
        self.timestamp = timestamp or time.time()
        self.handle = handle


class Chat:
    """Manages chat history and outbound message dispatch."""

    def __init__(self, max_history=500):
        self.history = collections.deque(maxlen=max_history)
        self.on_send = None  # async callback: on_send(text)

    def add_message(self, text, sender, timestamp=None, handle=None):
        msg = ChatMessage(text, sender, timestamp, handle)
        self.history.append(msg)
        return msg

    async def send(self, text):
        """Send a local message (adds to history + fires callback).

        Returns the ChatMessage or None if text was empty.
        """
        if not text.strip():
            return None
        msg = self.add_message(text, "local")
        if self.on_send:
            await self.on_send(text)
        return msg

    def receive(self, text, timestamp=None, handle=None):
        """Receive a remote message."""
        return self.add_message(text, "remote", timestamp, handle)

    def get_history(self, count=None):
        if count is None:
            return list(self.history)
        return list(self.history)[-count:]

    @staticmethod
    def format_message(msg):
        t = time.strftime("%H:%M", time.localtime(msg.timestamp))
        if msg.handle:
            tag = msg.handle
        else:
            tag = "You" if msg.sender == "local" else "Peer"
        return f"[{t}] {tag}: {msg.text}"
