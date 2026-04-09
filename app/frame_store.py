from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import cv2
import numpy as np

from app.config import Settings
from app.recognition import crop_roi, preprocess_direction_image, preprocess_floor_image


@dataclass
class FrameStore:
    settings: Settings
    _frame: np.ndarray | None = field(default=None, init=False)
    _captured_at: datetime | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def update(self, frame: np.ndarray) -> None:
        async with self._lock:
            self._frame = frame.copy()
            self._captured_at = datetime.now(tz=UTC)

    async def get_jpeg(self, *, overlay: bool = False) -> bytes | None:
        async with self._lock:
            if self._frame is None:
                return None
            frame = self._frame.copy()
            captured_at = self._captured_at

        if overlay:
            self._draw_roi(frame, captured_at)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return encoded.tobytes()

    async def get_roi_jpeg(self, kind: str, *, processed: bool = False) -> bytes | None:
        image = await self.get_roi_image(kind, processed=processed)
        if image is None:
            return None
        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            return None
        return encoded.tobytes()

    async def get_roi_image(self, kind: str, *, processed: bool = False) -> np.ndarray | None:
        async with self._lock:
            if self._frame is None:
                return None
            frame = self._frame.copy()

        roi = self.settings.floor_roi if kind == "floor" else self.settings.direction_roi
        image = crop_roi(frame, roi)
        if processed:
            if kind == "floor":
                image = preprocess_floor_image(image)
            else:
                image = preprocess_direction_image(image)
        return image

    async def get_size(self) -> tuple[int, int] | None:
        async with self._lock:
            if self._frame is None:
                return None
            height, width = self._frame.shape[:2]
        return width, height

    def _draw_roi(self, frame: np.ndarray, captured_at: datetime | None) -> None:
        floor = self.settings.floor_roi
        direction = self.settings.direction_roi
        floor_points = np.array(floor.corners(), dtype=np.int32)
        direction_points = np.array(direction.corners(), dtype=np.int32)
        cv2.polylines(frame, [floor_points], isClosed=True, color=(64, 220, 96), thickness=3)
        cv2.putText(
            frame,
            "floor",
            (floor.x, max(24, floor.y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (64, 220, 96),
            2,
            cv2.LINE_AA,
        )
        cv2.polylines(
            frame,
            [direction_points],
            isClosed=True,
            color=(255, 180, 40),
            thickness=3,
        )
        cv2.putText(
            frame,
            "direction",
            (direction.x, direction.y + direction.h + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 180, 40),
            2,
            cv2.LINE_AA,
        )
        if captured_at is not None:
            stamp = captured_at.astimezone().strftime("captured %Y-%m-%d %H:%M:%S")
            cv2.putText(
                frame,
                stamp,
                (24, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
