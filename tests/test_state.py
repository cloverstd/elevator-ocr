from datetime import UTC, datetime

from app.models import RecognitionResult
from app.state import StateManager


async def test_state_manager_debounces_frames() -> None:
    manager = StateManager(elevator_id="e1", stable_frames=3, heartbeat_seconds=30)
    observed_at = datetime.now(tz=UTC)

    changed = await manager.ingest_recognition(
        RecognitionResult(floor="3", direction="up", confidence=96.0, observed_at=observed_at)
    )
    assert changed is False

    changed = await manager.ingest_recognition(
        RecognitionResult(floor="3", direction="up", confidence=96.0, observed_at=observed_at)
    )
    assert changed is False

    changed = await manager.ingest_recognition(
        RecognitionResult(floor="3", direction="up", confidence=96.0, observed_at=observed_at)
    )
    assert changed is True

    snapshot = await manager.snapshot()
    assert snapshot.floor == "3"
    assert snapshot.direction == "up"
