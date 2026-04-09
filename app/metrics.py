from __future__ import annotations

from dataclasses import dataclass, field

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, Counter, generate_latest

from app.models import ElevatorState, ElevatorStatePayload


@dataclass
class Metrics:
    registry: CollectorRegistry = field(default_factory=CollectorRegistry)

    def __post_init__(self) -> None:
        self.stream_connected = Gauge(
            "elevator_stream_connected",
            "Whether the RTSP stream is connected.",
            ["elevator_id"],
            registry=self.registry,
        )
        self.current_floor = Gauge(
            "elevator_current_floor",
            "Current floor encoded as a one-hot gauge.",
            ["elevator_id", "floor"],
            registry=self.registry,
        )
        self.direction = Gauge(
            "elevator_direction",
            "Current direction encoded as a one-hot gauge.",
            ["elevator_id", "direction"],
            registry=self.registry,
        )
        self.last_update = Gauge(
            "elevator_last_update_unixtime",
            "Unix timestamp of the last state update.",
            ["elevator_id"],
            registry=self.registry,
        )
        self.ocr_success_total = Counter(
            "elevator_ocr_success_total",
            "Total OCR successes.",
            ["elevator_id"],
            registry=self.registry,
        )
        self.ocr_failure_total = Counter(
            "elevator_ocr_failure_total",
            "Total OCR failures.",
            ["elevator_id"],
            registry=self.registry,
        )
        self.state_changes_total = Counter(
            "elevator_state_changes_total",
            "Total stable state changes.",
            ["elevator_id"],
            registry=self.registry,
        )
        self._active_floor: dict[str, str] = {}
        self._active_direction: dict[str, str] = {}

    def record_recognition(self, elevator_id: str, success: bool) -> None:
        counter = self.ocr_success_total if success else self.ocr_failure_total
        counter.labels(elevator_id=elevator_id).inc()

    def record_state(self, state: ElevatorState | ElevatorStatePayload, changed: bool) -> None:
        elevator_id = state.elevator_id
        self.stream_connected.labels(elevator_id=elevator_id).set(
            1 if state.stream_connected else 0
        )
        self.last_update.labels(elevator_id=elevator_id).set(state.published_ts.timestamp())

        previous_floor = self._active_floor.get(elevator_id)
        if previous_floor and previous_floor != state.floor:
            self.current_floor.remove(elevator_id, previous_floor)
        if state.floor:
            self.current_floor.labels(elevator_id=elevator_id, floor=state.floor).set(1)
            self._active_floor[elevator_id] = state.floor
        else:
            self._active_floor.pop(elevator_id, None)

        previous_direction = self._active_direction.get(elevator_id)
        if previous_direction and previous_direction != state.direction:
            self.direction.remove(elevator_id, previous_direction)
        self.direction.labels(elevator_id=elevator_id, direction=state.direction).set(1)
        self._active_direction[elevator_id] = state.direction

        if changed:
            self.state_changes_total.labels(elevator_id=elevator_id).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST
