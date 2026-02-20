"""Webcam capture with real-time ASCII conversion."""

import cv2
import numpy as np
import threading
import time

# Brightness-to-character ramp (dark → light)
ASCII_RAMP = " .,:;i1tfLCG08@"
RAMP_LEN = len(ASCII_RAMP)


class AsciiCamera:
    """Captures webcam frames and converts them to ASCII art in a background thread."""

    def __init__(self, width, height, device=0):
        self.width = width
        self.height = height
        self.device = device
        self.enabled = True
        self.cap = None
        self.running = False
        self.current_frame = None
        self.current_color_frame = None
        self.lock = threading.Lock()
        self.thread = None

    @staticmethod
    def enumerate_cameras(max_index=10):
        """Probe camera indices 0..max_index-1 and return list of available indices."""
        available = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def start(self):
        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {self.device}. Check camera permissions.")

        # Lower resolution for speed
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def switch_camera(self, device):
        """Stop capture, switch to a new device index, and restart."""
        # Validate new device before releasing the old one
        test_cap = cv2.VideoCapture(device)
        if not test_cap.isOpened():
            test_cap.release()
            raise RuntimeError(f"Camera {device} not available")
        test_cap.release()

        was_running = self.running
        if was_running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=2)
            if self.cap:
                self.cap.release()
                self.cap = None
        self.device = device
        with self.lock:
            self.current_frame = None
            self.current_color_frame = None
        if was_running and self.enabled:
            self.start()

    def disable(self):
        """Disable camera capture and clear frame buffers."""
        self.enabled = False
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        if self.cap:
            self.cap.release()
            self.cap = None
        with self.lock:
            self.current_frame = None
            self.current_color_frame = None

    def enable(self):
        """Re-enable camera capture and restart."""
        self.enabled = True
        if not self.running:
            self.start()

    def _capture_loop(self):
        while self.running:
            if not self.enabled:
                time.sleep(0.1)
                continue
            ret, frame = self.cap.read()
            if not ret:
                continue

            # Flip horizontally for mirror effect
            frame = cv2.flip(frame, 1)

            ascii_lines, color_data = self._frame_to_ascii(frame)
            with self.lock:
                self.current_frame = ascii_lines
                self.current_color_frame = color_data

    def _frame_to_ascii(self, frame):
        """Convert a BGR frame to ASCII lines + per-character ANSI color codes."""
        # Resize to terminal panel dimensions
        small = cv2.resize(frame, (self.width, self.height))

        # Grayscale for character selection
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # Map brightness to ASCII index
        indices = (gray.astype(np.float32) / 256.0 * RAMP_LEN).astype(np.int32)
        indices = np.clip(indices, 0, RAMP_LEN - 1)

        lines = []
        colors = []
        for y in range(self.height):
            row_chars = []
            row_colors = []
            for x in range(self.width):
                ch = ASCII_RAMP[indices[y, x]]
                row_chars.append(ch)

                # Convert BGR → RGB → ANSI 256 color
                b, g, r = int(small[y, x, 0]), int(small[y, x, 1]), int(small[y, x, 2])
                ansi = 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)
                row_colors.append(ansi)

            lines.append("".join(row_chars))
            colors.append(row_colors)

        return lines, colors

    def get_frame(self):
        """Return (ascii_lines, color_data) or (None, None)."""
        with self.lock:
            return self.current_frame, self.current_color_frame

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()
