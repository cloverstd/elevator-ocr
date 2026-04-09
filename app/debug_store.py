from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.models import RecognitionDebugPayload, RecognitionResult


@dataclass
class RecognitionDebugStore:
    _result: RecognitionResult | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def update(self, result: RecognitionResult) -> None:
        async with self._lock:
            self._result = result

    async def snapshot(self) -> RecognitionDebugPayload | None:
        async with self._lock:
            if self._result is None:
                return None
            return RecognitionDebugPayload.from_result(self._result)
