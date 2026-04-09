from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import ROI


def _parse_roi(value: Any) -> ROI:
    if isinstance(value, ROI):
        return value
    if isinstance(value, dict):
        return ROI(
            int(value["x"]),
            int(value["y"]),
            int(value["w"]),
            int(value["h"]),
            float(value.get("angle", 0.0)),
        )
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        if len(parts) == 4:
            return ROI(*(int(part) for part in parts))
        if len(parts) == 5:
            return ROI(
                int(parts[0]),
                int(parts[1]),
                int(parts[2]),
                int(parts[3]),
                float(parts[4]),
            )
        raise ValueError("ROI must contain x,y,w,h or x,y,w,h,angle")
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return ROI(*(int(part) for part in value))
    if isinstance(value, (tuple, list)) and len(value) == 5:
        return ROI(
            int(value[0]),
            int(value[1]),
            int(value[2]),
            int(value[3]),
            float(value[4]),
        )
    raise ValueError("Invalid ROI value")


def _parse_allowed_floors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            loaded = json.loads(value)
            return [str(item) for item in loaded]
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError("Invalid ALLOWED_FLOORS value")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        enable_decoding=False,
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    data_dir: str = "data"
    model_dir: str = "data/models"

    rtsp_url: str = "rtsp://example.com/stream"
    rtsp_transport: Literal["tcp", "udp"] = "tcp"
    rtsp_flush_frames: int = 8
    elevator_id: str = "elevator-1"
    floor_roi: ROI = Field(default_factory=lambda: ROI(0, 0, 160, 80))
    direction_roi: ROI = Field(default_factory=lambda: ROI(160, 0, 80, 80))
    allowed_floors: list[str] = Field(
        default_factory=lambda: ["-2", "-1", "1", "2", "3", "4", "5"]
    )
    sample_interval_ms: int = 500
    stable_frames: int = 3
    disconnect_timeout_seconds: int = 10

    mqtt_broker_url: str = "mqtt://localhost:1883"
    mqtt_topic_state: str = "elevator/state"
    mqtt_heartbeat_seconds: int = 30
    mqtt_client_id: str = "elevator-ocr"

    tesseract_cmd: str | None = None
    direction_match_threshold: float = 0.70
    floor_sample_match_threshold: float = 0.74
    direction_sample_match_threshold: float = 0.72
    floor_model_min_confidence: float = 0.75
    direction_model_min_confidence: float = 0.75
    log_level: str = "INFO"

    @field_validator("floor_roi", "direction_roi", mode="before")
    @classmethod
    def validate_roi(cls, value: Any) -> ROI:
        return _parse_roi(value)

    @field_validator("allowed_floors", mode="before")
    @classmethod
    def validate_allowed_floors(cls, value: Any) -> list[str]:
        return _parse_allowed_floors(value)

    @field_validator("rtsp_transport", mode="before")
    @classmethod
    def validate_rtsp_transport(cls, value: Any) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"tcp", "udp"}:
                return normalized
        raise ValueError("RTSP_TRANSPORT must be tcp or udp")


PERSISTED_CONFIG_FIELDS = tuple(field_name for field_name in Settings.model_fields if field_name != "data_dir")


def roi_to_text(roi: ROI) -> str:
    return f"{roi.x},{roi.y},{roi.w},{roi.h},{roi.angle:.1f}"


def settings_to_persisted_dict(settings: Settings) -> dict[str, Any]:
    payload = settings.model_dump(mode="python")
    return {field_name: payload[field_name] for field_name in PERSISTED_CONFIG_FIELDS}


def settings_to_api_dict(settings: Settings) -> dict[str, Any]:
    payload = settings.model_dump(mode="python")
    payload["allowed_floors_text"] = ",".join(settings.allowed_floors)
    payload["floor_roi_text"] = roi_to_text(settings.floor_roi)
    payload["direction_roi_text"] = roi_to_text(settings.direction_roi)
    return payload


def build_settings_from_payload(current: Settings, payload: dict[str, Any]) -> Settings:
    merged = current.model_dump(mode="python")
    for key, value in payload.items():
        if key not in Settings.model_fields or key == "data_dir":
            continue
        if key in {"floor_roi", "direction_roi"}:
            merged[key] = _parse_roi(value)
        elif key == "allowed_floors":
            merged[key] = _parse_allowed_floors(value)
        else:
            merged[key] = value
    return Settings(**merged)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
