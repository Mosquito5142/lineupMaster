"""อัดเสียงจากไมค์ระหว่างกดปุ่มค้าง (push-to-talk).

เปิดไมค์แบบ shared mode ตามปกติของ Windows — เสียงคุยในเกมยังใช้ได้พร้อมกัน
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd


class PushToTalkRecorder:
    def __init__(self, cfg: dict) -> None:
        self.samplerate = int(cfg.get("samplerate", 16000))
        self.device = cfg.get("device")
        self.max_seconds = float(cfg.get("max_seconds", 10))
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._frames = 0
        self._max_frames = int(self.samplerate * self.max_seconds)

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, _frames, _time, _status) -> None:
        with self._lock:
            if self._frames >= self._max_frames:
                return
            self._chunks.append(indata[:, 0].copy())
            self._frames += len(indata)

    def start(self) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
            self._frames = 0
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            device=self.device,
            blocksize=0,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)
