from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time

import cv2
import numpy as np

from app.feedback_store import FeedbackStore, PendingSampleRecord
from app.models import ROI


def _signature(image: np.ndarray) -> np.ndarray:
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    return blurred.astype(np.float32) / 255.0


@dataclass(slots=True)
class AutoCaptureManager:
    feedback_store: FeedbackStore
    min_interval_seconds: float = 1.0
    change_threshold: float = 0.045
    strong_change_threshold: float = 0.090
    _last_floor_signature: np.ndarray | None = field(default=None, init=False)
    _last_saved_at: float = field(default=0.0, init=False)
    _last_prediction: str | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def maybe_capture_floor(
        self,
        image: np.ndarray,
        *,
        predicted_label: str | None,
        confidence: float | None,
        elevator_id: str,
        roi: ROI,
    ) -> str | None:
        if image.size == 0:
            return None

        now = time.monotonic()
        signature = _signature(image)
        async with self._lock:
            changed = self._has_changed(signature, predicted_label)
            if not changed:
                return None
            if now - self._last_saved_at < self.min_interval_seconds:
                return None

            ok, encoded = cv2.imencode(".jpg", image)
            if not ok:
                return None
            image_path = self.feedback_store.save_pending_sample("floor", encoded.tobytes())
            pending_id = self.feedback_store.insert_pending(
                PendingSampleRecord(
                    kind="floor",
                    predicted_label=predicted_label,
                    confidence=confidence,
                    elevator_id=elevator_id,
                    roi={
                        "x": roi.x,
                        "y": roi.y,
                        "w": roi.w,
                        "h": roi.h,
                        "angle": roi.angle,
                    },
                    image_path=image_path,
                )
            )
            self._last_floor_signature = signature
            self._last_saved_at = now
            self._last_prediction = predicted_label
            return pending_id

    def _has_changed(self, signature: np.ndarray, predicted_label: str | None) -> bool:
        if self._last_floor_signature is None:
            return True
        delta = float(np.mean(np.abs(signature - self._last_floor_signature)))
        if predicted_label != self._last_prediction and delta >= self.change_threshold:
            return True
        return delta >= self.strong_change_threshold
