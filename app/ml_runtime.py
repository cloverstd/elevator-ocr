from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import Settings
from app.models import RecognitionCandidate

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ClassifierPrediction:
    label: str
    confidence: float


def normalize_for_classifier(image: np.ndarray, image_size: tuple[int, int]) -> np.ndarray:
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, image_size, interpolation=cv2.INTER_AREA)
    normalized = scaled.astype(np.float32) / 255.0
    return normalized[np.newaxis, np.newaxis, :, :]


class OptionalClassifier:
    def __init__(self, task: str, settings: Settings) -> None:
        self.task = task
        self.settings = settings
        self.enabled = False
        self.image_size = (96, 96)
        self.labels: list[str] = []
        self._model: Any = None
        self._torch: Any = None
        self._load()

    def _load(self) -> None:
        self.enabled = False
        self.labels = []
        self._model = None
        self._torch = None
        metadata_path = Path(self.settings.model_dir) / f"{self.task}_metadata.json"
        weights_path = Path(self.settings.model_dir) / f"{self.task}_model.pt"
        if not metadata_path.exists() or not weights_path.exists():
            return

        try:
            import torch
            from app.ml_model import SmallClassifier
        except ImportError:
            logger.info("Torch is not installed; ML classifier for %s disabled", self.task)
            return

        metadata = json.loads(metadata_path.read_text())
        self.labels = [str(label) for label in metadata["labels"]]
        self.image_size = (int(metadata["image_width"]), int(metadata["image_height"]))

        model = SmallClassifier(len(self.labels))
        state = torch.load(weights_path, map_location="cpu")
        model.load_state_dict(state)
        model.eval()

        self._torch = torch
        self._model = model
        self.enabled = True
        logger.info("Loaded %s classifier with %d labels", self.task, len(self.labels))

    def reload(self) -> bool:
        self._load()
        return self.enabled

    def predict(self, image: np.ndarray) -> ClassifierPrediction | None:
        if not self.enabled or self._model is None or self._torch is None:
            return None

        tensor = self._torch.from_numpy(normalize_for_classifier(image, self.image_size))
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=1)[0]
            confidence, index = self._torch.max(probs, dim=0)

        return ClassifierPrediction(
            label=self.labels[int(index.item())],
            confidence=float(confidence.item()),
        )

    def predict_topk(self, image: np.ndarray, limit: int = 3) -> list[RecognitionCandidate]:
        if not self.enabled or self._model is None or self._torch is None:
            return []

        tensor = self._torch.from_numpy(normalize_for_classifier(image, self.image_size))
        with self._torch.no_grad():
            logits = self._model(tensor)
            probs = self._torch.softmax(logits, dim=1)[0]
            topk = min(limit, len(self.labels))
            values, indices = self._torch.topk(probs, k=topk)

        return [
            RecognitionCandidate(
                label=self.labels[int(index.item())],
                score=float(value.item()),
                source="model",
            )
            for value, index in zip(values, indices, strict=False)
        ]
