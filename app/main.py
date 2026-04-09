from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from app.auto_capture import AutoCaptureManager
from app.backup import BackupManager
from app.config import Settings, get_settings
from app.debug_store import RecognitionDebugStore
from app.feedback_models import (
    PendingBatchLabelRequest,
    FeedbackRequest,
    FloorCoverageResponse,
    FeedbackStatsResponse,
    PendingLabelRequest,
    PendingSampleListResponse,
    PendingSampleResponse,
    PendingStatsResponse,
    TrainingRequest,
    TrainingStatusResponse,
)
from app.feedback_store import FeedbackRecord, FeedbackStore
from app.frame_store import FrameStore
from app.metrics import Metrics
from app.ml_runtime import OptionalClassifier
from app.models import ElevatorStatePayload, RecognitionDebugPayload
from app.mqtt import MqttPublisher
from app.recognition import FrameRecognizer, SamplePrototypeMatcher
from app.rtsp import RtspWorker
from app.state import StateManager
from app.training import TrainingManager
from app.web import INDEX_HTML

logging.basicConfig(level=logging.INFO)


class AppServices:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metrics = Metrics()
        self.frame_store = FrameStore(settings)
        self.debug_store = RecognitionDebugStore()
        self.feedback_store = FeedbackStore(settings)
        self.backup = BackupManager(settings.data_dir)
        self.auto_capture = AutoCaptureManager(self.feedback_store)
        self.floor_sample_matcher = SamplePrototypeMatcher("floor", settings, self.feedback_store)
        self.direction_sample_matcher = SamplePrototypeMatcher("direction", settings, self.feedback_store)
        self.floor_classifier = OptionalClassifier("floor", settings)
        self.direction_classifier = OptionalClassifier("direction", settings)
        self.state_manager = StateManager(
            elevator_id=settings.elevator_id,
            stable_frames=settings.stable_frames,
            heartbeat_seconds=settings.mqtt_heartbeat_seconds,
        )
        self.mqtt = MqttPublisher(settings)
        self.recognizer = FrameRecognizer(
            settings,
            floor_sample_matcher=self.floor_sample_matcher,
            direction_sample_matcher=self.direction_sample_matcher,
            floor_classifier=self.floor_classifier,
            direction_classifier=self.direction_classifier,
        )
        self.training = TrainingManager(settings.data_dir, self.reload_model)
        self.training.set_model_loaded("floor", self.floor_classifier.enabled)
        self.training.set_model_loaded("direction", self.direction_classifier.enabled)
        self.rtsp_worker = RtspWorker(
            settings=settings,
            recognizer=self.recognizer,
            state_manager=self.state_manager,
            metrics=self.metrics,
            frame_store=self.frame_store,
            auto_capture=self.auto_capture,
            debug_store=self.debug_store,
        )
        self.heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        def listener(payload: ElevatorStatePayload, changed: bool) -> None:
            self.metrics.record_state(payload, changed)
            self.mqtt.publish_state(payload)

        await self.state_manager.add_listener(listener)
        self.mqtt.start()
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="heartbeat-loop")
        await self.rtsp_worker.start()

    async def stop(self) -> None:
        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.training.stop()
        await self.rtsp_worker.stop()
        self.mqtt.stop()

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            await self.state_manager.publish_heartbeat_if_due()

    async def reload_model(self, task: str) -> bool:
        if task == "floor":
            return self.floor_classifier.reload()
        if task == "direction":
            return self.direction_classifier.reload()
        return False

    async def reload_sample_matchers(self) -> None:
        self.floor_sample_matcher.reload()
        self.direction_sample_matcher.reload()

    async def reload_models(self) -> dict[str, bool]:
        floor_loaded = self.floor_classifier.reload()
        direction_loaded = self.direction_classifier.reload()
        self.training.set_model_loaded("floor", floor_loaded)
        self.training.set_model_loaded("direction", direction_loaded)
        return {
            "floor_loaded": floor_loaded,
            "direction_loaded": direction_loaded,
        }


def create_app(settings: Settings | None = None, *, start_runtime: bool = True) -> FastAPI:
    resolved_settings = settings or get_settings()
    services = AppServices(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_runtime:
            await services.start()
        yield
        if start_runtime:
            await services.stop()

    app = FastAPI(title="Elevator OCR", lifespan=lifespan)
    app.state.services = services

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/v1/state", response_model=ElevatorStatePayload)
    async def state() -> ElevatorStatePayload:
        return await services.state_manager.snapshot()

    @app.get("/api/v1/events/stream")
    async def events_stream() -> StreamingResponse:
        queue = await services.state_manager.subscribe()

        async def event_generator():
            try:
                while True:
                    payload = await queue.get()
                    yield f"event: state\ndata: {payload.model_dump_json()}\n\n"
            finally:
                await services.state_manager.unsubscribe(queue)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(
            content=services.metrics.render(),
            media_type=services.metrics.content_type,
        )

    @app.get("/api/v1/frame.jpg")
    async def frame(overlay: bool = Query(default=False)) -> Response:
        image = await services.frame_store.get_jpeg(overlay=overlay)
        if image is None:
            return Response(status_code=404)
        return Response(content=image, media_type="image/jpeg")

    @app.get("/api/v1/frame/{kind}.jpg")
    async def frame_roi(kind: str, processed: bool = Query(default=False)) -> Response:
        if kind not in {"floor", "direction"}:
            return Response(status_code=404)
        image = await services.frame_store.get_roi_jpeg(kind, processed=processed)
        if image is None:
            return Response(status_code=404)
        return Response(content=image, media_type="image/jpeg")

    @app.get("/api/v1/debug/recognition", response_model=RecognitionDebugPayload | None)
    async def recognition_debug() -> RecognitionDebugPayload | None:
        return await services.debug_store.snapshot()

    @app.get("/api/v1/roi")
    async def roi() -> JSONResponse:
        frame_size = await services.frame_store.get_size()
        floor_roi = services.settings.floor_roi
        direction_roi = services.settings.direction_roi
        payload = {
            "floor_roi": {
                "x": floor_roi.x,
                "y": floor_roi.y,
                "w": floor_roi.w,
                "h": floor_roi.h,
                "angle": floor_roi.angle,
            },
            "direction_roi": {
                "x": direction_roi.x,
                "y": direction_roi.y,
                "w": direction_roi.w,
                "h": direction_roi.h,
                "angle": direction_roi.angle,
            },
            "frame_size": (
                {"width": frame_size[0], "height": frame_size[1]}
                if frame_size is not None
                else None
            ),
        }
        return JSONResponse(payload)

    @app.get("/api/v1/feedback/stats", response_model=FeedbackStatsResponse)
    async def feedback_stats() -> FeedbackStatsResponse:
        return FeedbackStatsResponse.model_validate(services.feedback_store.stats())

    @app.get("/api/v1/feedback/coverage", response_model=FloorCoverageResponse)
    async def feedback_coverage() -> FloorCoverageResponse:
        return FloorCoverageResponse.model_validate(
            services.feedback_store.floor_coverage(services.settings.allowed_floors)
        )

    @app.get("/api/v1/backup/export")
    async def export_backup() -> Response:
        payload = services.backup.export_zip()
        filename = f"elevator-ocr-backup-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/v1/backup/import")
    async def import_backup(request: Request) -> JSONResponse:
        payload = await request.body()
        if not payload:
            return JSONResponse({"error": "empty backup payload"}, status_code=400)
        try:
            services.backup.import_zip(payload)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        await services.reload_sample_matchers()
        loaded = await services.reload_models()
        return JSONResponse({"status": "ok", **loaded})

    @app.post("/api/v1/feedback")
    async def feedback(request: FeedbackRequest) -> JSONResponse:
        snapshot = await services.state_manager.snapshot()
        image_bytes = await services.frame_store.get_roi_jpeg(request.kind)
        if image_bytes is None:
            return JSONResponse({"error": "frame unavailable"}, status_code=409)

        roi = services.settings.floor_roi if request.kind == "floor" else services.settings.direction_roi
        predicted_label = snapshot.floor if request.kind == "floor" else snapshot.direction
        sample_path = services.feedback_store.save_sample(request.kind, image_bytes)
        services.feedback_store.insert_label(
            FeedbackRecord(
                kind=request.kind,
                predicted_label=predicted_label,
                confirmed_label=request.label,
                confidence=snapshot.ocr_confidence,
                elevator_id=snapshot.elevator_id,
                roi={
                    "x": roi.x,
                    "y": roi.y,
                    "w": roi.w,
                    "h": roi.h,
                    "angle": roi.angle,
                },
                image_path=sample_path,
                accepted_prediction=request.accepted_prediction,
            )
        )
        await services.reload_sample_matchers()
        return JSONResponse({"status": "ok", "saved_to": sample_path})

    @app.get("/api/v1/pending/stats", response_model=PendingStatsResponse)
    async def pending_stats() -> PendingStatsResponse:
        return PendingStatsResponse.model_validate(services.feedback_store.pending_stats())

    @app.get("/api/v1/pending/next", response_model=PendingSampleResponse | None)
    async def next_pending(
        kind: str = Query(default="floor"),
        order: str = Query(default="newest"),
    ) -> PendingSampleResponse | None:
        if kind not in {"floor", "direction"}:
            return None
        if order not in {"newest", "hard"}:
            order = "newest"
        sample = services.feedback_store.next_pending_by_order(kind, order=order)
        if sample is None:
            return None
        return PendingSampleResponse.model_validate(
            {
                **sample,
                "image_url": f"/api/v1/pending/{sample['id']}.jpg",
            }
        )

    @app.get("/api/v1/pending/list", response_model=PendingSampleListResponse)
    async def list_pending(
        kind: str = Query(default="floor"),
        status: str = Query(default="pending"),
        order: str = Query(default="newest"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> PendingSampleListResponse:
        if kind not in {"floor", "direction"} or status not in {"pending", "labeled"}:
            return PendingSampleListResponse(items=[])
        if order not in {"newest", "hard"}:
            order = "newest"
        samples = services.feedback_store.list_pending(kind, status=status, order=order, limit=limit, offset=offset)
        return PendingSampleListResponse(
            items=[
                PendingSampleResponse.model_validate(
                    {
                        **sample,
                        "image_url": f"/api/v1/pending/{sample['id']}.jpg",
                    }
                )
                for sample in samples
            ]
        )

    @app.get("/api/v1/pending/{sample_id}.jpg")
    async def pending_image(sample_id: str) -> Response:
        image_path = services.feedback_store.pending_image_path(sample_id)
        if image_path is None:
            return Response(status_code=404)
        return Response(content=Path(image_path).read_bytes(), media_type="image/jpeg")

    @app.post("/api/v1/pending/{sample_id}/label")
    async def label_pending(sample_id: str, request: PendingLabelRequest) -> JSONResponse:
        saved = services.feedback_store.label_pending(
            sample_id,
            confirmed_label=request.confirmed_label,
            accepted_prediction=request.accepted_prediction,
        )
        if not saved:
            return JSONResponse({"error": "pending sample not found"}, status_code=404)
        await services.reload_sample_matchers()
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/pending/batch-label")
    async def batch_label_pending(request: PendingBatchLabelRequest) -> JSONResponse:
        accepted = services.feedback_store.batch_accept_pending(request.sample_ids, kind="floor")
        await services.reload_sample_matchers()
        return JSONResponse({"status": "ok", "accepted": accepted})

    @app.get("/api/v1/training/status", response_model=TrainingStatusResponse)
    async def training_status() -> TrainingStatusResponse:
        return TrainingStatusResponse.model_validate(services.training.snapshot())

    @app.post("/api/v1/training")
    async def training(request: TrainingRequest) -> JSONResponse:
        try:
            services.training.start(
                request.task,
                epochs=request.epochs,
                batch_size=request.batch_size,
                lr=request.lr,
                image_size=request.image_size,
            )
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse({"status": "started", "task": request.task})

    @app.post("/api/v1/models/reload")
    async def reload_models() -> JSONResponse:
        loaded = await services.reload_models()
        services.training.set_model_loaded("floor", loaded["floor_loaded"], "model reloaded manually")
        services.training.set_model_loaded("direction", loaded["direction_loaded"], "model reloaded manually")
        return JSONResponse(
            {
                "status": "ok",
                **loaded,
            }
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    return app


app = create_app()
