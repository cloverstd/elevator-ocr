from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
import math
from typing import Literal

from pydantic import BaseModel


Direction = Literal["up", "down", "idle", "unknown"]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(slots=True)
class ROI:
    x: int
    y: int
    w: int
    h: int
    angle: float = 0.0

    def as_slice(self) -> tuple[slice, slice]:
        return slice(self.y, self.y + self.h), slice(self.x, self.x + self.w)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def corners(self) -> list[tuple[float, float]]:
        cx, cy = self.center
        half_w = self.w / 2.0
        half_h = self.h / 2.0
        radians = math.radians(self.angle)
        cos_a = math.cos(radians)
        sin_a = math.sin(radians)
        points = [
            (-half_w, -half_h),
            (half_w, -half_h),
            (half_w, half_h),
            (-half_w, half_h),
        ]
        return [
            (
                cx + (dx * cos_a) - (dy * sin_a),
                cy + (dx * sin_a) + (dy * cos_a),
            )
            for dx, dy in points
        ]


@dataclass(slots=True)
class RecognitionCandidate:
    label: str
    score: float
    source: str


@dataclass(slots=True)
class RecognitionResult:
    floor: str | None
    direction: Direction
    confidence: float | None
    observed_at: datetime
    floor_source: str = "unknown"
    direction_source: str = "unknown"
    floor_candidates: list[RecognitionCandidate] = field(default_factory=list)
    direction_candidates: list[RecognitionCandidate] = field(default_factory=list)


@dataclass(slots=True)
class ElevatorState:
    elevator_id: str
    floor: str | None = None
    direction: Direction = "unknown"
    source_ts: datetime = field(default_factory=utcnow)
    published_ts: datetime = field(default_factory=utcnow)
    stream_connected: bool = False
    ocr_confidence: float | None = None

    def with_updates(self, **changes: object) -> "ElevatorState":
        return replace(self, **changes)


class ElevatorStatePayload(BaseModel):
    elevator_id: str
    floor: str | None
    direction: Direction
    source_ts: datetime
    published_ts: datetime
    stream_connected: bool
    ocr_confidence: float | None

    @classmethod
    def from_state(cls, state: ElevatorState) -> "ElevatorStatePayload":
        return cls.model_validate(asdict(state))


class RecognitionCandidatePayload(BaseModel):
    label: str
    score: float
    source: str


class RecognitionDebugPayload(BaseModel):
    floor: str | None
    direction: Direction
    confidence: float | None
    observed_at: datetime
    floor_source: str
    direction_source: str
    floor_candidates: list[RecognitionCandidatePayload]
    direction_candidates: list[RecognitionCandidatePayload]

    @classmethod
    def from_result(cls, result: RecognitionResult) -> "RecognitionDebugPayload":
        return cls(
            floor=result.floor,
            direction=result.direction,
            confidence=result.confidence,
            observed_at=result.observed_at,
            floor_source=result.floor_source,
            direction_source=result.direction_source,
            floor_candidates=[
                RecognitionCandidatePayload(
                    label=item.label,
                    score=item.score,
                    source=item.source,
                )
                for item in result.floor_candidates
            ],
            direction_candidates=[
                RecognitionCandidatePayload(
                    label=item.label,
                    score=item.score,
                    source=item.source,
                )
                for item in result.direction_candidates
            ],
        )
