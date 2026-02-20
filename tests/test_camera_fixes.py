"""Tests for ascii_camera.py bug fixes.

Fix 1: enable() race condition — should not call start() when already running.
Fix 2: switch_camera() validation — should reject invalid device before releasing old.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import threading


class TestEnableRaceCondition(unittest.TestCase):
    """Fix 1: enable() must not call start() if already running."""

    def _make_camera(self, running=False):
        """Create an AsciiCamera with mocked cv2 so no real device is needed."""
        with patch("ascii_camera.cv2"):
            from ascii_camera import AsciiCamera
            cam = AsciiCamera(80, 24, device=0)
            cam.running = running
            return cam

    @patch("ascii_camera.cv2")
    def test_enable_when_not_running_calls_start(self, mock_cv2):
        """enable() should call start() when camera is not running."""
        from ascii_camera import AsciiCamera
        cam = AsciiCamera(80, 24, device=0)
        cam.running = False

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        cam.enable()

        self.assertTrue(cam.enabled)
        self.assertTrue(cam.running)
        mock_cv2.VideoCapture.assert_called_once_with(0)
        # Cleanup
        cam.running = False
        if cam.thread:
            cam.thread.join(timeout=1)

    @patch("ascii_camera.cv2")
    def test_enable_when_already_running_skips_start(self, mock_cv2):
        """enable() should NOT call start() when camera is already running."""
        from ascii_camera import AsciiCamera
        cam = AsciiCamera(80, 24, device=0)
        cam.running = True  # Simulate already running

        cam.enable()

        self.assertTrue(cam.enabled)
        # VideoCapture should NOT have been called — start() was skipped
        mock_cv2.VideoCapture.assert_not_called()

    @patch("ascii_camera.cv2")
    def test_enable_disable_enable_cycle(self, mock_cv2):
        """Repeated enable/disable/enable should not create duplicate captures."""
        from ascii_camera import AsciiCamera
        cam = AsciiCamera(80, 24, device=0)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        # First enable
        cam.enable()
        self.assertTrue(cam.running)
        first_call_count = mock_cv2.VideoCapture.call_count

        # Disable
        cam.disable()
        self.assertFalse(cam.running)

        # Re-enable — should open a new capture
        cam.enable()
        self.assertTrue(cam.running)
        self.assertEqual(mock_cv2.VideoCapture.call_count, first_call_count + 1)

        # Cleanup
        cam.running = False
        if cam.thread:
            cam.thread.join(timeout=1)


class TestSwitchCameraValidation(unittest.TestCase):
    """Fix 2: switch_camera() must validate new device before releasing old."""

    @patch("ascii_camera.cv2")
    def test_switch_to_invalid_device_raises_and_keeps_old(self, mock_cv2):
        """Switching to an invalid camera should raise and keep the old one."""
        from ascii_camera import AsciiCamera
        cam = AsciiCamera(80, 24, device=0)

        # Simulate the validation probe failing
        mock_test_cap = MagicMock()
        mock_test_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_test_cap

        cam.running = True
        cam.cap = MagicMock()  # Simulate old camera is open

        with self.assertRaises(RuntimeError) as ctx:
            cam.switch_camera(99)

        self.assertIn("99", str(ctx.exception))
        # Old camera should NOT have been released
        cam.cap.release.assert_not_called()
        # Device should still be 0
        self.assertEqual(cam.device, 0)
        # Should still be running
        self.assertTrue(cam.running)

    @patch("ascii_camera.cv2")
    def test_switch_to_valid_device_succeeds(self, mock_cv2):
        """Switching to a valid camera should work and release the old one."""
        from ascii_camera import AsciiCamera
        cam = AsciiCamera(80, 24, device=0)

        # First call: validation probe (succeeds)
        # Second call: actual start()
        mock_test_cap = MagicMock()
        mock_test_cap.isOpened.return_value = True
        mock_test_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_test_cap

        old_cap = MagicMock()
        cam.cap = old_cap
        cam.running = True
        # Create a started (and finished) thread so join() doesn't raise
        t = threading.Thread(target=lambda: None)
        t.start()
        t.join()
        cam.thread = t

        cam.switch_camera(1)

        # New device should be set
        self.assertEqual(cam.device, 1)
        # Old capture should have been released
        old_cap.release.assert_called_once()

        # Cleanup
        cam.running = False
        if cam.thread and cam.thread.is_alive():
            cam.thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
