from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    kind: Literal["floor", "direction"]
    label: str
    accepted_prediction: bool = False


class FeedbackStatsResponse(BaseModel):
    floor: int
    direction: int


class FloorCoverageItem(BaseModel):
    floor: str
    count: int


class FloorCoverageResponse(BaseModel):
    total_labeled: int
    covered_floors: int
    total_floors: int
    items: list[FloorCoverageItem] = Field(default_factory=list)


class PendingSampleResponse(BaseModel):
    id: str
    kind: Literal["floor", "direction"]
    status: Literal["pending", "labeled"] = "pending"
    predicted_label: str | None
    confirmed_label: str | None = None
    confidence: float | None
    created_at: datetime
    labeled_at: datetime | None = None
    image_url: str


class PendingSampleListResponse(BaseModel):
    items: list[PendingSampleResponse]


class PendingStatsResponse(BaseModel):
    floor: int
    direction: int


class PendingLabelRequest(BaseModel):
    confirmed_label: str
    accepted_prediction: bool = False


class PendingBatchLabelRequest(BaseModel):
    sample_ids: list[str] = Field(default_factory=list)


class TrainingRequest(BaseModel):
    task: Literal["floor", "direction"]
    epochs: int = Field(default=18, ge=1, le=500)
    batch_size: int = Field(default=32, ge=1, le=1024)
    lr: float = Field(default=1e-3, gt=0, le=1.0)
    image_size: int = Field(default=96, ge=16, le=512)


class TrainingHistoryPoint(BaseModel):
    finished_at: datetime
    accuracy: float
    num_samples: int | None = None


class TrainingTaskStatus(BaseModel):
    task: Literal["floor", "direction"]
    state: Literal["idle", "running", "succeeded", "failed"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    log_tail: list[str] = Field(default_factory=list)
    model_loaded: bool = False
    num_samples: int | None = None
    last_accuracy: float | None = None
    previous_accuracy: float | None = None
    accuracy_trend: Literal["better", "same", "worse"] | None = None
    history: list[TrainingHistoryPoint] = Field(default_factory=list)


class TrainingStatusResponse(BaseModel):
    floor: TrainingTaskStatus
    direction: TrainingTaskStatus
