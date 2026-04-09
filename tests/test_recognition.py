from pathlib import Path

import cv2
import numpy as np

from app.config import Settings
from app.feedback_store import FeedbackRecord, FeedbackStore
from app.recognition import (
    SamplePrototypeMatcher,
    detect_direction,
    find_split_positions,
    normalize_floor_text,
)


def test_normalize_floor_text_accepts_negative_floors() -> None:
    allowed = ["-2", "-1", "1", "2", "12"]
    assert normalize_floor_text("-01", allowed) == "-1"
    assert normalize_floor_text("012", allowed) == "12"
    assert normalize_floor_text("B1", allowed) is None


def test_detect_direction_identifies_idle_blank_image() -> None:
    blank = np.zeros((64, 64, 3), dtype=np.uint8)
    direction, score = detect_direction(blank, threshold=0.7)
    assert direction == "idle"
    assert score == 1.0


def test_find_split_positions_prefers_center_valley() -> None:
    col_sum = np.array([0, 5, 20, 40, 60, 55, 20, 8, 5, 18, 45, 60, 58, 35, 10, 0])
    assert find_split_positions(col_sum) == [8]


def test_floor_sample_matcher_prefers_labeled_fixed_font_samples(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), allowed_floors=["35", "18", "9"])
    store = FeedbackStore(settings)

    image = np.zeros((40, 80, 3), dtype=np.uint8)
    cv2.putText(image, "35", (4, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    sample_path = store.save_sample("floor", encoded.tobytes())
    store.insert_label(
        FeedbackRecord(
            kind="floor",
            predicted_label="9",
            confirmed_label="35",
            confidence=55.0,
            elevator_id="e1",
            roi={"x": 0, "y": 0, "w": 80, "h": 40, "angle": 0.0},
            image_path=sample_path,
            accepted_prediction=False,
        )
    )

    matcher = SamplePrototypeMatcher("floor", settings, store)
    label, confidence = matcher.predict(image)
    assert label == "35"
    assert confidence is not None
    assert confidence > 0.74
