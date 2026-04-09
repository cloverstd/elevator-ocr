from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.models import ElevatorState, ElevatorStatePayload, RecognitionResult, utcnow


StateListener = Callable[[ElevatorStatePayload, bool], Awaitable[None] | None]


class StateManager:
    def __init__(
        self,
        elevator_id: str,
        stable_frames: int,
        heartbeat_seconds: int,
    ) -> None:
        self._state = ElevatorState(elevator_id=elevator_id)
        self._stable_frames = stable_frames
        self._heartbeat_seconds = heartbeat_seconds
        self._candidate_key: tuple[str | None, str] | None = None
        self._candidate_confidence: float | None = None
        self._candidate_seen_at = self._state.source_ts
        self._candidate_count = 0
        self._listeners: list[StateListener] = []
        self._subscribers: set[asyncio.Queue[ElevatorStatePayload]] = set()
        self._last_publish_monotonic = time.monotonic()
        self._lock = asyncio.Lock()

    async def add_listener(self, listener: StateListener) -> None:
        async with self._lock:
            self._listeners.append(listener)

    async def snapshot(self) -> ElevatorStatePayload:
        async with self._lock:
            return ElevatorStatePayload.from_state(self._state)

    async def subscribe(self) -> asyncio.Queue[ElevatorStatePayload]:
        queue: asyncio.Queue[ElevatorStatePayload] = asyncio.Queue(maxsize=8)
        async with self._lock:
            queue.put_nowait(ElevatorStatePayload.from_state(self._state))
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[ElevatorStatePayload]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def set_stream_connected(self, connected: bool) -> None:
        async with self._lock:
            if self._state.stream_connected == connected:
                return
            self._state = self._state.with_updates(
                stream_connected=connected,
                published_ts=utcnow(),
            )
            payload = ElevatorStatePayload.from_state(self._state)
            listeners = list(self._listeners)
            subscribers = list(self._subscribers)
            self._last_publish_monotonic = time.monotonic()
        await self._broadcast(payload, listeners, subscribers, changed=True)

    async def ingest_recognition(self, result: RecognitionResult) -> bool:
        async with self._lock:
            candidate_floor = result.floor if result.floor is not None else self._state.floor
            candidate_direction = (
                result.direction
                if result.direction != "unknown"
                else self._state.direction
            )
            if candidate_floor is None and candidate_direction == "unknown":
                return False

            candidate_key = (candidate_floor, candidate_direction)
            if candidate_key == self._candidate_key:
                self._candidate_count += 1
                if result.confidence is not None:
                    self._candidate_confidence = result.confidence
                    self._candidate_seen_at = result.observed_at
            else:
                self._candidate_key = candidate_key
                self._candidate_count = 1
                self._candidate_confidence = result.confidence
                self._candidate_seen_at = result.observed_at

            current_key = (self._state.floor, self._state.direction)
            if self._candidate_count < self._stable_frames or candidate_key == current_key:
                return False

            self._state = self._state.with_updates(
                floor=candidate_floor,
                direction=candidate_direction,
                source_ts=self._candidate_seen_at,
                published_ts=utcnow(),
                ocr_confidence=self._candidate_confidence,
            )
            payload = ElevatorStatePayload.from_state(self._state)
            listeners = list(self._listeners)
            subscribers = list(self._subscribers)
            self._last_publish_monotonic = time.monotonic()
        await self._broadcast(payload, listeners, subscribers, changed=True)
        return True

    async def publish_heartbeat_if_due(self) -> bool:
        async with self._lock:
            now_monotonic = time.monotonic()
            if now_monotonic - self._last_publish_monotonic < self._heartbeat_seconds:
                return False
            self._state = self._state.with_updates(published_ts=utcnow())
            payload = ElevatorStatePayload.from_state(self._state)
            listeners = list(self._listeners)
            subscribers = list(self._subscribers)
            self._last_publish_monotonic = now_monotonic
        await self._broadcast(payload, listeners, subscribers, changed=False)
        return True

    async def force_state(
        self,
        *,
        floor: str | None,
        direction: str,
        stream_connected: bool,
        confidence: float | None = None,
    ) -> None:
        async with self._lock:
            timestamp = utcnow()
            self._state = self._state.with_updates(
                floor=floor,
                direction=direction,
                stream_connected=stream_connected,
                source_ts=timestamp,
                published_ts=timestamp,
                ocr_confidence=confidence,
            )
            payload = ElevatorStatePayload.from_state(self._state)
            listeners = list(self._listeners)
            subscribers = list(self._subscribers)
            self._last_publish_monotonic = time.monotonic()
        await self._broadcast(payload, listeners, subscribers, changed=True)

    async def _broadcast(
        self,
        payload: ElevatorStatePayload,
        listeners: list[StateListener],
        subscribers: list[asyncio.Queue[ElevatorStatePayload]],
        *,
        changed: bool,
    ) -> None:
        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)

        for listener in listeners:
            result = listener(payload, changed)
            if asyncio.iscoroutine(result):
                await result
