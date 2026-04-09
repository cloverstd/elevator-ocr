from httpx import ASGITransport, AsyncClient
import numpy as np
from pathlib import Path

import cv2
from app.config import Settings
from app.config_store import ConfigStore
from app.feedback_store import FeedbackRecord, PendingSampleRecord
from app.main import create_app
from app.models import RecognitionCandidate, RecognitionResult, utcnow


async def test_state_endpoint_returns_latest_state() -> None:
    settings = Settings(
        elevator_id="e1",
        allowed_floors=["-2", "-1", "1", "2"],
    )
    app = create_app(settings, start_runtime=False)
    await app.state.services.state_manager.force_state(
        floor="-1",
        direction="down",
        stream_connected=True,
        confidence=88.0,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["floor"] == "-1"
    assert payload["direction"] == "down"
    assert payload["stream_connected"] is True


async def test_metrics_endpoint_exposes_floor_label() -> None:
    settings = Settings(
        elevator_id="e1",
        allowed_floors=["-2", "-1", "1", "2"],
    )
    app = create_app(settings, start_runtime=False)
    await app.state.services.state_manager.add_listener(
        lambda payload, changed: app.state.services.metrics.record_state(payload, changed)
    )
    await app.state.services.state_manager.force_state(
        floor="2",
        direction="up",
        stream_connected=True,
        confidence=91.0,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert 'elevator_current_floor{elevator_id="e1",floor="2"} 1.0' in response.text


async def test_frame_roi_endpoint_returns_jpeg() -> None:
    settings = Settings()
    app = create_app(settings, start_runtime=False)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    await app.state.services.frame_store.update(frame)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/frame/floor.jpg")

    assert response.status_code == 200
    assert response.content[:2] == b"\xff\xd8"


async def test_feedback_endpoint_persists_sample_and_stats(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        elevator_id="e1",
        allowed_floors=["-2", "-1", "1", "2", "35"],
    )
    app = create_app(settings, start_runtime=False)
    frame = np.full((120, 160, 3), 180, dtype=np.uint8)
    await app.state.services.frame_store.update(frame)
    await app.state.services.state_manager.force_state(
        floor="35",
        direction="up",
        stream_connected=True,
        confidence=96.0,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/feedback",
            json={
                "kind": "floor",
                "label": "35",
                "accepted_prediction": True,
            },
        )
        stats_response = await client.get("/api/v1/feedback/stats")

    assert response.status_code == 200
    payload = response.json()
    saved_to = Path(payload["saved_to"])
    assert saved_to.exists()
    assert saved_to.suffix == ".jpg"

    assert stats_response.status_code == 200
    assert stats_response.json() == {"floor": 1, "direction": 0}

    db_path = tmp_path / "data" / "labels.db"
    assert db_path.exists()


async def test_training_status_endpoint_returns_idle_state(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=str(tmp_path / "data")), start_runtime=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/training/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["floor"]["state"] == "idle"
    assert payload["direction"]["state"] == "idle"
    assert payload["floor"]["last_accuracy"] is None
    assert payload["floor"]["previous_accuracy"] is None
    assert payload["floor"]["accuracy_trend"] is None


async def test_model_reload_endpoint_returns_flags() -> None:
    app = create_app(Settings(), start_runtime=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/models/reload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "floor_loaded" in payload
    assert "direction_loaded" in payload


async def test_config_endpoint_persists_to_database(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        save_response = await client.post(
            "/api/v1/config",
            json={
                "rtsp_url": "rtsp://camera/new",
                "rtsp_transport": "udp",
                "floor_roi": "10,20,30,40,5",
                "direction_roi": "50,60,70,80,-3",
                "allowed_floors": "-2,-1,1,2,35",
                "sample_interval_ms": 300,
                "mqtt_topic_state": "demo/elevator/state",
            },
        )
        config_response = await client.get("/api/v1/config")
        roi_response = await client.get("/api/v1/roi")

    assert save_response.status_code == 200
    assert config_response.status_code == 200
    payload = config_response.json()
    assert payload["rtsp_url"] == "rtsp://camera/new"
    assert payload["rtsp_transport"] == "udp"
    assert payload["allowed_floors"] == ["-2", "-1", "1", "2", "35"]
    assert roi_response.json()["floor_roi"]["angle"] == 5.0

    loaded = ConfigStore(Settings(data_dir=str(tmp_path / "data"))).load_settings(
        Settings(data_dir=str(tmp_path / "data"))
    )
    assert loaded.rtsp_url == "rtsp://camera/new"
    assert loaded.floor_roi.x == 10
    assert loaded.direction_roi.angle == -3.0


async def test_pending_sample_roundtrip(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    image = np.full((32, 48, 3), 200, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
    pending_id = app.state.services.feedback_store.insert_pending(
        PendingSampleRecord(
            kind="floor",
            predicted_label="35",
            confidence=88.0,
            elevator_id="e1",
            roi={"x": 1, "y": 2, "w": 3, "h": 4, "angle": 0.0},
            image_path=image_path,
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        next_response = await client.get("/api/v1/pending/next?kind=floor")
        stats_before = await client.get("/api/v1/pending/stats")
        image_response = await client.get(f"/api/v1/pending/{pending_id}.jpg")
        label_response = await client.post(
            f"/api/v1/pending/{pending_id}/label",
            json={"confirmed_label": "35", "accepted_prediction": True},
        )
        stats_after = await client.get("/api/v1/pending/stats")
        feedback_stats = await client.get("/api/v1/feedback/stats")

    assert next_response.status_code == 200
    assert next_response.json()["id"] == pending_id
    assert stats_before.json() == {"floor": 1, "direction": 0}
    assert image_response.status_code == 200
    assert image_response.content[:2] == b"\xff\xd8"
    assert label_response.status_code == 200
    assert stats_after.json() == {"floor": 0, "direction": 0}
    assert feedback_stats.json() == {"floor": 1, "direction": 0}


async def test_pending_list_endpoint_returns_history_items(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    for label in ("12", "35"):
        image = np.full((24, 36, 3), 120, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
        app.state.services.feedback_store.insert_pending(
            PendingSampleRecord(
                kind="floor",
                predicted_label=label,
                confidence=80.0,
                elevator_id="e1",
                roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
                image_path=image_path,
            )
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/pending/list?kind=floor&limit=10")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["predicted_label"] == "35"
    assert items[1]["predicted_label"] == "12"


async def test_pending_list_endpoint_can_prioritize_hard_samples(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    for label, confidence in (("12", 92.0), ("35", 41.0), ("18", None)):
        image = np.full((24, 36, 3), 120, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
        app.state.services.feedback_store.insert_pending(
            PendingSampleRecord(
                kind="floor",
                predicted_label=label,
                confidence=confidence,
                elevator_id="e1",
                roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
                image_path=image_path,
            )
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/pending/list?kind=floor&status=pending&order=hard&limit=10")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["predicted_label"] for item in items] == ["18", "35", "12"]


async def test_pending_list_endpoint_can_show_labeled_items(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    image = np.full((24, 36, 3), 120, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
    pending_id = app.state.services.feedback_store.insert_pending(
        PendingSampleRecord(
            kind="floor",
            predicted_label="18",
            confidence=80.0,
            elevator_id="e1",
            roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
            image_path=image_path,
        )
    )
    app.state.services.feedback_store.label_pending(
        pending_id,
        confirmed_label="18",
        accepted_prediction=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/pending/list?kind=floor&status=labeled&limit=10")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "labeled"
    assert items[0]["confirmed_label"] == "18"


async def test_labeled_sample_can_be_relabeled(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    image = np.full((24, 36, 3), 120, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
    pending_id = app.state.services.feedback_store.insert_pending(
        PendingSampleRecord(
            kind="floor",
            predicted_label="18",
            confidence=80.0,
            elevator_id="e1",
            roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
            image_path=image_path,
        )
    )
    app.state.services.feedback_store.label_pending(
        pending_id,
        confirmed_label="18",
        accepted_prediction=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        relabel_response = await client.post(
            f"/api/v1/pending/{pending_id}/label",
            json={"confirmed_label": "19", "accepted_prediction": False},
        )
        labeled_list_response = await client.get("/api/v1/pending/list?kind=floor&status=labeled&limit=10")

    assert relabel_response.status_code == 200
    item = labeled_list_response.json()["items"][0]
    assert item["confirmed_label"] == "19"


async def test_feedback_coverage_endpoint_reports_counts_per_floor(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), allowed_floors=["-2", "-1", "1", "2", "35"])
    app = create_app(settings, start_runtime=False)

    for label in ("35", "35", "-1"):
        image = np.full((24, 36, 3), 120, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        image_path = app.state.services.feedback_store.save_sample("floor", encoded.tobytes())
        app.state.services.feedback_store.insert_label(
            FeedbackRecord(
                kind="floor",
                predicted_label=label,
                confirmed_label=label,
                confidence=88.0,
                elevator_id="e1",
                roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
                image_path=image_path,
                accepted_prediction=True,
            )
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/feedback/coverage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["covered_floors"] == 2
    assert payload["total_floors"] == 5
    counts = {item["floor"]: item["count"] for item in payload["items"]}
    assert counts["35"] == 2
    assert counts["-1"] == 1
    assert counts["2"] == 0


async def test_backup_export_import_roundtrip(tmp_path: Path) -> None:
    source_app = create_app(
        Settings(data_dir=str(tmp_path / "source-data"), allowed_floors=["-1", "1", "35"]),
        start_runtime=False,
    )
    image = np.full((24, 36, 3), 120, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    image_path = source_app.state.services.feedback_store.save_sample("floor", encoded.tobytes())
    source_app.state.services.feedback_store.insert_label(
        FeedbackRecord(
            kind="floor",
            predicted_label="35",
            confirmed_label="35",
            confidence=91.0,
            elevator_id="e1",
            roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
            image_path=image_path,
            accepted_prediction=True,
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=source_app),
        base_url="http://testserver",
    ) as client:
        export_response = await client.get("/api/v1/backup/export")

    target_app = create_app(
        Settings(data_dir=str(tmp_path / "target-data"), allowed_floors=["-1", "1", "35"]),
        start_runtime=False,
    )
    async with AsyncClient(
        transport=ASGITransport(app=target_app),
        base_url="http://testserver",
    ) as client:
        import_response = await client.post(
            "/api/v1/backup/import",
            content=export_response.content,
            headers={"Content-Type": "application/zip"},
        )
        stats_response = await client.get("/api/v1/feedback/stats")

    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"
    assert import_response.status_code == 200
    assert stats_response.json() == {"floor": 1, "direction": 0}


async def test_pending_batch_label_accepts_selected_predictions(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"))
    app = create_app(settings, start_runtime=False)

    pending_ids: list[str] = []
    for label in ("18", "35"):
        image = np.full((24, 36, 3), 120, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        assert ok
        image_path = app.state.services.feedback_store.save_pending_sample("floor", encoded.tobytes())
        pending_ids.append(
            app.state.services.feedback_store.insert_pending(
                PendingSampleRecord(
                    kind="floor",
                    predicted_label=label,
                    confidence=80.0,
                    elevator_id="e1",
                    roi={"x": 0, "y": 0, "w": 10, "h": 10, "angle": 0.0},
                    image_path=image_path,
                )
            )
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        batch_response = await client.post(
            "/api/v1/pending/batch-label",
            json={"sample_ids": pending_ids},
        )
        pending_stats = await client.get("/api/v1/pending/stats")
        feedback_stats = await client.get("/api/v1/feedback/stats")
        labeled_list = await client.get("/api/v1/pending/list?kind=floor&status=labeled&limit=10")

    assert batch_response.status_code == 200
    assert batch_response.json()["accepted"] == 2
    assert pending_stats.json() == {"floor": 0, "direction": 0}
    assert feedback_stats.json() == {"floor": 2, "direction": 0}
    assert {item["confirmed_label"] for item in labeled_list.json()["items"]} == {"18", "35"}


async def test_recognition_debug_endpoint_returns_sources_and_candidates() -> None:
    app = create_app(Settings(), start_runtime=False)
    await app.state.services.debug_store.update(
        RecognitionResult(
            floor="35",
            direction="up",
            confidence=93.0,
            observed_at=utcnow(),
            floor_source="sample",
            direction_source="model",
            floor_candidates=[
                RecognitionCandidate(label="35", score=0.93, source="sample"),
                RecognitionCandidate(label="18", score=0.72, source="sample"),
            ],
            direction_candidates=[
                RecognitionCandidate(label="up", score=0.87, source="model"),
                RecognitionCandidate(label="down", score=0.12, source="model"),
            ],
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/debug/recognition")

    assert response.status_code == 200
    payload = response.json()
    assert payload["floor_source"] == "sample"
    assert payload["direction_source"] == "model"
    assert payload["floor_candidates"][0]["label"] == "35"
    assert payload["direction_candidates"][0]["label"] == "up"
