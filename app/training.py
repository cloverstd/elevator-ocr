from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Awaitable, Callable, Literal

from app.feedback_models import TrainingHistoryPoint, TrainingTaskStatus

logger = logging.getLogger(__name__)


TrainingTask = Literal["floor", "direction"]
ReloadCallback = Callable[[TrainingTask], Awaitable[bool]]


@dataclass(slots=True)
class _MutableStatus:
    task: TrainingTask
    state: Literal["idle", "running", "succeeded", "failed"] = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    log_tail: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    model_loaded: bool = False
    num_samples: int | None = None
    last_accuracy: float | None = None
    previous_accuracy: float | None = None
    accuracy_trend: Literal["better", "same", "worse"] | None = None
    history: list[TrainingHistoryPoint] = field(default_factory=list)
    runner: asyncio.Task[None] | None = None

    def to_response(self) -> TrainingTaskStatus:
        return TrainingTaskStatus(
            task=self.task,
            state=self.state,
            started_at=self.started_at,
            finished_at=self.finished_at,
            message=self.message,
            log_tail=list(self.log_tail),
            model_loaded=self.model_loaded,
            num_samples=self.num_samples,
            last_accuracy=self.last_accuracy,
            previous_accuracy=self.previous_accuracy,
            accuracy_trend=self.accuracy_trend,
            history=self.history,
        )


class TrainingManager:
    def __init__(self, data_dir: str, reload_model: ReloadCallback) -> None:
        self.data_dir = data_dir
        self.reload_model = reload_model
        self.repo_root = Path(__file__).resolve().parents[1]
        self.statuses: dict[TrainingTask, _MutableStatus] = {
            "floor": _MutableStatus(task="floor"),
            "direction": _MutableStatus(task="direction"),
        }

    def snapshot(self) -> dict[TrainingTask, TrainingTaskStatus]:
        return {task: status.to_response() for task, status in self.statuses.items()}

    def set_model_loaded(self, task: TrainingTask, loaded: bool, message: str | None = None) -> None:
        status = self.statuses[task]
        status.model_loaded = loaded
        if message is not None:
            status.message = message
        self._load_metadata(task, status)

    def start(
        self,
        task: TrainingTask,
        *,
        epochs: int,
        batch_size: int,
        lr: float,
        image_size: int,
    ) -> None:
        status = self.statuses[task]
        if status.runner is not None and not status.runner.done():
            raise RuntimeError(f"{task} training is already running")

        status.state = "running"
        status.started_at = datetime.now(tz=UTC)
        status.finished_at = None
        status.message = "training started"
        status.log_tail.clear()
        status.model_loaded = False
        status.num_samples = None
        status.previous_accuracy = status.last_accuracy if status.last_accuracy is not None else self._latest_history_accuracy(status)
        status.last_accuracy = None
        status.accuracy_trend = None
        status.runner = asyncio.create_task(
            self._run(
                task,
                epochs=epochs,
                batch_size=batch_size,
                lr=lr,
                image_size=image_size,
            ),
            name=f"train-{task}",
        )

    async def stop(self) -> None:
        for status in self.statuses.values():
            if status.runner is not None and not status.runner.done():
                status.runner.cancel()
                try:
                    await status.runner
                except asyncio.CancelledError:
                    pass

    async def _run(
        self,
        task: TrainingTask,
        *,
        epochs: int,
        batch_size: int,
        lr: float,
        image_size: int,
    ) -> None:
        status = self.statuses[task]
        command = [
            sys.executable,
            "scripts/train_classifier.py",
            "--data-dir",
            self.data_dir,
            "--task",
            task,
            "--epochs",
            str(epochs),
            "--batch-size",
            str(batch_size),
            "--lr",
            str(lr),
            "--image-size",
            str(image_size),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.repo_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert process.stdout is not None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    status.log_tail.append(text)

            return_code = await process.wait()
            status.finished_at = datetime.now(tz=UTC)
            status.last_accuracy = self._extract_accuracy(status.log_tail)
            if return_code != 0:
                status.state = "failed"
                status.message = f"training failed with exit code {return_code}"
                return

            model_loaded = await self.reload_model(task)
            status.state = "succeeded"
            status.model_loaded = model_loaded
            self._load_metadata(task, status)
            status.accuracy_trend = self._compare_accuracy(status.previous_accuracy, status.last_accuracy)
            self._append_history(task, status)
            status.message = "training finished and model reloaded" if model_loaded else "training finished but model not loaded"
        except asyncio.CancelledError:
            status.state = "failed"
            status.finished_at = datetime.now(tz=UTC)
            status.message = "training cancelled"
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("Training failed for task=%s", task)
            status.state = "failed"
            status.finished_at = datetime.now(tz=UTC)
            status.message = str(exc)

    def _metadata_path(self, task: TrainingTask) -> Path:
        return self.repo_root / self.data_dir / "models" / f"{task}_metadata.json"

    def _load_metadata(self, task: TrainingTask, status: _MutableStatus) -> None:
        path = self._metadata_path(task)
        if not path.exists():
            return
        try:
            metadata = json.loads(path.read_text())
        except Exception:  # pragma: no cover
            logger.exception("Failed to load training metadata for task=%s", task)
            return
        value = metadata.get("num_samples")
        status.num_samples = int(value) if value is not None else None
        accuracy = metadata.get("last_accuracy")
        status.last_accuracy = float(accuracy) if accuracy is not None else status.last_accuracy
        raw_history = metadata.get("history", [])
        history: list[TrainingHistoryPoint] = []
        for item in raw_history[-8:]:
            try:
                history.append(TrainingHistoryPoint.model_validate(item))
            except Exception:
                continue
        status.history = history

    @staticmethod
    def _extract_accuracy(lines: deque[str]) -> float | None:
        for line in reversed(lines):
            marker = "acc="
            if marker not in line:
                continue
            try:
                return float(line.split(marker, 1)[1].split()[0])
            except ValueError:
                continue
        return None

    @staticmethod
    def _compare_accuracy(previous: float | None, current: float | None) -> Literal["better", "same", "worse"] | None:
        if previous is None or current is None:
            return None
        if current - previous > 0.003:
            return "better"
        if previous - current > 0.003:
            return "worse"
        return "same"

    @staticmethod
    def _latest_history_accuracy(status: _MutableStatus) -> float | None:
        if not status.history:
            return None
        return status.history[-1].accuracy

    def _append_history(self, task: TrainingTask, status: _MutableStatus) -> None:
        if status.last_accuracy is None or status.finished_at is None:
            return
        path = self._metadata_path(task)
        if not path.exists():
            return
        try:
            metadata = json.loads(path.read_text())
        except Exception:  # pragma: no cover
            logger.exception("Failed to update training history for task=%s", task)
            return
        history = list(metadata.get("history", []))
        history.append(
            {
                "finished_at": status.finished_at.isoformat(),
                "accuracy": status.last_accuracy,
                "num_samples": status.num_samples,
            }
        )
        metadata["history"] = history[-8:]
        path.write_text(json.dumps(metadata, indent=2))
        self._load_metadata(task, status)
