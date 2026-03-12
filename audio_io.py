"""Audio capture and playback for P2P voice chat.

Uses sounddevice for mic/speaker I/O with raw PCM (16 kHz, mono, 16-bit).
Audio chunks are 60 ms (960 samples = 1920 bytes), well under Veilid's 64 KB
message limit even after base64 encoding + JSON framing.
"""

import base64
import collections
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_MS = 60
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)  # 960
JITTER_BUF_MAX = 8  # max queued chunks before dropping old ones


class AudioCapture:
    """Captures microphone audio in a background stream."""

    def __init__(self, sample_rate=SAMPLE_RATE, channels=CHANNELS, chunk_ms=CHUNK_MS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_samples = int(sample_rate * chunk_ms / 1000)
        self.enabled = False
        self._stream = None
        self._lock = threading.Lock()
        self._chunk = None  # latest captured chunk (bytes)
        self._seq = 0

    def start(self):
        self.enabled = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=DTYPE,
            blocksize=self.chunk_samples,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        self.enabled = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time_info, status):
        if not self.enabled:
            return
        pcm_bytes = indata.tobytes()
        with self._lock:
            self._seq += 1
            self._chunk = pcm_bytes

    def get_chunk(self):
        """Return (seq, pcm_bytes) or (None, None) if nothing new."""
        with self._lock:
            if self._chunk is None:
                return None, None
            seq, data = self._seq, self._chunk
            self._chunk = None
            return seq, data

    @staticmethod
    def list_devices():
        """Return list of input device names."""
        devices = sd.query_devices()
        inputs = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                inputs.append(f"{i}: {d['name']}")
        return inputs


class AudioPlayback:
    """Plays received audio chunks through the speaker with a small jitter buffer."""

    def __init__(self, sample_rate=SAMPLE_RATE, channels=CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.enabled = True
        self._stream = None
        self._lock = threading.Lock()
        self._buffer = collections.deque(maxlen=JITTER_BUF_MAX)
        self._playing = False

    def start(self):
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=DTYPE,
            blocksize=CHUNK_SAMPLES,
            callback=self._callback,
        )
        self._stream.start()
        self._playing = True

    def stop(self):
        self._playing = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def enqueue(self, pcm_bytes):
        """Add a decoded audio chunk to the jitter buffer."""
        if not self.enabled:
            return
        with self._lock:
            self._buffer.append(pcm_bytes)

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self._buffer:
                chunk = self._buffer.popleft()
            else:
                chunk = None

        if chunk is not None:
            samples = np.frombuffer(chunk, dtype=np.int16)
            # Pad or trim to match requested frames
            if len(samples) < frames:
                padded = np.zeros(frames, dtype=np.int16)
                padded[: len(samples)] = samples
                outdata[:] = padded.reshape(-1, 1)
            else:
                outdata[:] = samples[:frames].reshape(-1, 1)
        else:
            outdata.fill(0)


def encode_audio_packet(seq, pcm_bytes):
    """Encode a PCM chunk into a dict ready for JSON serialization."""
    return {
        "t": "a",
        "seq": seq,
        "d": base64.b64encode(pcm_bytes).decode("ascii"),
    }


def decode_audio_packet(msg):
    """Decode an audio packet dict back to (seq, pcm_bytes)."""
    return msg["seq"], base64.b64decode(msg["d"])
