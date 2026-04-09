from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.auto_capture import AutoCaptureManager
from app.config import Settings
from app.debug_store import RecognitionDebugStore
from app.frame_store import FrameStore
from app.metrics import Metrics
from app.recognition import FrameRecognizer, crop_roi
from app.state import StateManager
from app.models import utcnow

logger = logging.getLogger(__name__)


def _open_capture(url: str, transport: str) -> cv2.VideoCapture:
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;{transport}|fflags;nobuffer|flags;low_delay|max_delay;500000"
    )
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


@dataclass
class LatestFrameReader:
    capture: cv2.VideoCapture
    flush_frames: int
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _frame: np.ndarray | None = field(default=None, init=False)
    _frame_id: int = field(default=0, init=False)
    _last_frame_monotonic: float | None = field(default=None, init=False)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="latest-frame-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.capture.release()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def snapshot(self) -> tuple[int, float | None, np.ndarray | None]:
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            return self._frame_id, self._last_frame_monotonic, frame

    def _run(self) -> None:
        while not self._stop_event.is_set():
            ok, frame = self._read_latest_frame()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            with self._lock:
                self._frame = frame
                self._frame_id += 1
                self._last_frame_monotonic = time.monotonic()

    def _read_latest_frame(self) -> tuple[bool, np.ndarray | None]:
        grabbed = False
        frame = None
        ok = False

        for _ in range(max(1, self.flush_frames)):
            grabbed = self.capture.grab()
            if not grabbed:
                break
            ok, frame = self.capture.retrieve()
            if not ok or frame is None:
                break

        if ok and frame is not None:
            return True, frame
        return self.capture.read()


@dataclass(slots=True)
class RtspWorker:
    settings: Settings
    recognizer: FrameRecognizer
    state_manager: StateManager
    metrics: Metrics
    frame_store: FrameStore
    auto_capture: AutoCaptureManager
    debug_store: RecognitionDebugStore
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    async def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="rtsp-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            capture = await asyncio.to_thread(
                _open_capture,
                self.settings.rtsp_url,
                self.settings.rtsp_transport,
            )
            if not capture.isOpened():
                logger.warning(
                    "Failed to open RTSP stream, retrying with transport=%s",
                    self.settings.rtsp_transport,
                )
                await self.state_manager.set_stream_connected(False)
                await asyncio.sleep(2)
                continue

            reader = LatestFrameReader(capture, flush_frames=self.settings.rtsp_flush_frames)
            reader.start()
            last_processed_frame_id = -1
            try:
                while not self._stop_event.is_set():
                    frame_id, last_frame_monotonic, frame = await asyncio.to_thread(reader.snapshot)
                    now_monotonic = time.monotonic()

                    if frame is None or last_frame_monotonic is None:
                        await self.state_manager.set_stream_connected(False)
                        await asyncio.sleep(0.05)
                        continue

                    if now_monotonic - last_frame_monotonic > self.settings.disconnect_timeout_seconds:
                        await self.state_manager.set_stream_connected(False)
                        logger.warning("RTSP stream stalled, reconnecting")
                        break

                    await self.state_manager.set_stream_connected(True)
                    if frame_id == last_processed_frame_id:
                        await asyncio.sleep(0.01)
                        continue

                    last_processed_frame_id = frame_id
                    await self.frame_store.update(frame)
                    observed_at = utcnow()
                    try:
                        result = self.recognizer.recognize(frame, observed_at)
                        await self.debug_store.update(result)
                        floor_crop = crop_roi(frame, self.settings.floor_roi)
                        await self.auto_capture.maybe_capture_floor(
                            floor_crop,
                            predicted_label=result.floor,
                            confidence=result.confidence,
                            elevator_id=self.settings.elevator_id,
                            roi=self.settings.floor_roi,
                        )
                        self.metrics.record_recognition(
                            self.settings.elevator_id,
                            success=result.floor is not None,
                        )
                        await self.state_manager.ingest_recognition(result)
                    except Exception:  # pragma: no cover - defensive runtime boundary
                        logger.exception("Frame recognition failed")
                        self.metrics.record_recognition(
                            self.settings.elevator_id,
                            success=False,
                        )
                    await asyncio.sleep(self.settings.sample_interval_ms / 1000)
            finally:
                await asyncio.to_thread(reader.stop)

            await asyncio.sleep(1)
