from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.config import Settings


FeedbackKind = Literal["floor", "direction"]


@dataclass(slots=True)
class FeedbackRecord:
    kind: FeedbackKind
    predicted_label: str | None
    confirmed_label: str
    confidence: float | None
    elevator_id: str
    roi: dict[str, int | float]
    image_path: str
    accepted_prediction: bool


@dataclass(slots=True)
class PendingSampleRecord:
    kind: FeedbackKind
    predicted_label: str | None
    confidence: float | None
    elevator_id: str
    roi: dict[str, int | float]
    image_path: str


class FeedbackStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_dir = Path(settings.data_dir)
        self.samples_dir = self.base_dir / "samples"
        self.db_path = self.base_dir / "labels.db"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS labels (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    predicted_label TEXT,
                    confirmed_label TEXT NOT NULL,
                    confidence REAL,
                    elevator_id TEXT NOT NULL,
                    roi_json TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    accepted_prediction INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_samples (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    predicted_label TEXT,
                    confidence REAL,
                    elevator_id TEXT NOT NULL,
                    roi_json TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    confirmed_label TEXT,
                    accepted_prediction INTEGER,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    labeled_at TEXT
                )
                """
            )
            connection.commit()

    def save_sample(self, kind: FeedbackKind, image_bytes: bytes, suffix: str = ".jpg") -> str:
        target_dir = self.samples_dir / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{suffix}"
        path = target_dir / filename
        path.write_bytes(image_bytes)
        return str(path)

    def save_pending_sample(self, kind: FeedbackKind, image_bytes: bytes, suffix: str = ".jpg") -> str:
        target_dir = self.samples_dir / "pending" / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{suffix}"
        path = target_dir / filename
        path.write_bytes(image_bytes)
        return str(path)

    def insert_label(self, record: FeedbackRecord) -> None:
        with sqlite3.connect(self.db_path) as connection:
            self._insert_label_with_connection(connection, record)
            connection.commit()

    def _insert_label_with_connection(self, connection: sqlite3.Connection, record: FeedbackRecord) -> None:
        connection.execute(
            """
            INSERT INTO labels (
                id, kind, predicted_label, confirmed_label, confidence,
                elevator_id, roi_json, image_path, accepted_prediction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                record.kind,
                record.predicted_label,
                record.confirmed_label,
                record.confidence,
                record.elevator_id,
                json.dumps(record.roi),
                record.image_path,
                1 if record.accepted_prediction else 0,
            ),
        )

    def insert_pending(self, record: PendingSampleRecord) -> str:
        pending_id = uuid.uuid4().hex
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO pending_samples (
                    id, kind, predicted_label, confidence, elevator_id,
                    roi_json, image_path, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    pending_id,
                    record.kind,
                    record.predicted_label,
                    record.confidence,
                    record.elevator_id,
                    json.dumps(record.roi),
                    record.image_path,
                ),
            )
            connection.commit()
        return pending_id

    def next_pending(self, kind: FeedbackKind) -> dict[str, object] | None:
        return self.next_pending_by_order(kind, order="newest")

    def next_pending_by_order(
        self,
        kind: FeedbackKind,
        *,
        order: Literal["newest", "hard"] = "newest",
    ) -> dict[str, object] | None:
        if order == "hard":
            order_clause = """
                ORDER BY
                    CASE WHEN confidence IS NULL THEN 0 ELSE 1 END ASC,
                    confidence ASC,
                    created_at DESC
            """
        else:
            order_clause = "ORDER BY created_at ASC"
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                f"""
                SELECT id, kind, predicted_label, confidence, created_at, image_path
                FROM pending_samples
                WHERE kind = ? AND status = 'pending'
                {order_clause}
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_pending(
        self,
        kind: FeedbackKind,
        *,
        status: Literal["pending", "labeled"] = "pending",
        order: Literal["newest", "hard"] = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        if status == "pending" and order == "hard":
            order_clause = """
                ORDER BY
                    CASE WHEN confidence IS NULL THEN 0 ELSE 1 END ASC,
                    confidence ASC,
                    created_at DESC
            """
        else:
            order_clause = "ORDER BY created_at DESC"
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT id, kind, status, predicted_label, confirmed_label, confidence, created_at, labeled_at, image_path
                FROM pending_samples
                WHERE kind = ? AND status = ?
                {order_clause}
                LIMIT ? OFFSET ?
                """,
                (kind, status, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_image_path(self, sample_id: str) -> str | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT image_path FROM pending_samples WHERE id = ?",
                (sample_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def label_pending(
        self,
        sample_id: str,
        *,
        confirmed_label: str,
        accepted_prediction: bool,
    ) -> bool:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT id, kind, predicted_label, confidence, elevator_id, roi_json, image_path, status
                FROM pending_samples
                WHERE id = ?
                """,
                (sample_id,),
            ).fetchone()
            if row is None:
                return False

            if row["status"] == "pending":
                self.insert_label(
                    FeedbackRecord(
                        kind=str(row["kind"]),
                        predicted_label=row["predicted_label"],
                        confirmed_label=confirmed_label,
                        confidence=row["confidence"],
                        elevator_id=str(row["elevator_id"]),
                        roi=json.loads(str(row["roi_json"])),
                        image_path=str(row["image_path"]),
                        accepted_prediction=accepted_prediction,
                    )
                )
            elif row["status"] == "labeled":
                connection.execute(
                    """
                    UPDATE labels
                    SET confirmed_label = ?,
                        accepted_prediction = ?
                    WHERE kind = ? AND image_path = ?
                    """,
                    (
                        confirmed_label,
                        1 if accepted_prediction else 0,
                        str(row["kind"]),
                        str(row["image_path"]),
                    ),
                )
            else:
                return False

            connection.execute(
                """
                UPDATE pending_samples
                SET status = 'labeled',
                    confirmed_label = ?,
                    accepted_prediction = ?,
                    labeled_at = ?
                WHERE id = ?
                """,
                (
                    confirmed_label,
                    1 if accepted_prediction else 0,
                    datetime.now(tz=UTC).isoformat(),
                    sample_id,
                ),
            )
            connection.commit()
        return True

    def batch_accept_pending(self, sample_ids: list[str], *, kind: FeedbackKind) -> int:
        accepted = 0
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT id, kind, predicted_label, confidence, elevator_id, roi_json, image_path, status
                FROM pending_samples
                WHERE kind = ? AND status = 'pending' AND id IN ({",".join("?" for _ in sample_ids)})
                """,
                (kind, *sample_ids),
            ).fetchall() if sample_ids else []

            for row in rows:
                predicted_label = row["predicted_label"]
                if not predicted_label:
                    continue
                self._insert_label_with_connection(
                    connection,
                    FeedbackRecord(
                        kind=str(row["kind"]),
                        predicted_label=predicted_label,
                        confirmed_label=str(predicted_label),
                        confidence=row["confidence"],
                        elevator_id=str(row["elevator_id"]),
                        roi=json.loads(str(row["roi_json"])),
                        image_path=str(row["image_path"]),
                        accepted_prediction=True,
                    )
                )
                connection.execute(
                    """
                    UPDATE pending_samples
                    SET status = 'labeled',
                        confirmed_label = ?,
                        accepted_prediction = 1,
                        labeled_at = ?
                    WHERE id = ?
                    """,
                    (
                        str(predicted_label),
                        datetime.now(tz=UTC).isoformat(),
                        str(row["id"]),
                    ),
                )
                accepted += 1
            connection.commit()
        return accepted

    def stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT kind, COUNT(*) FROM labels GROUP BY kind"
            ).fetchall()
        stats = {"floor": 0, "direction": 0}
        for kind, count in rows:
            stats[str(kind)] = int(count)
        return stats

    def labeled_samples(self, kind: FeedbackKind) -> list[dict[str, object]]:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT kind, confirmed_label, image_path
                FROM labels
                WHERE kind = ?
                ORDER BY created_at
                """,
                (kind,),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT kind, COUNT(*)
                FROM pending_samples
                WHERE status = 'pending'
                GROUP BY kind
                """
            ).fetchall()
        stats = {"floor": 0, "direction": 0}
        for kind, count in rows:
            stats[str(kind)] = int(count)
        return stats

    def floor_coverage(self, allowed_floors: list[str]) -> dict[str, object]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT confirmed_label, COUNT(*)
                FROM labels
                WHERE kind = 'floor'
                GROUP BY confirmed_label
                """
            ).fetchall()
        counts = {str(label): int(count) for label, count in rows}
        items = [{"floor": floor, "count": counts.get(floor, 0)} for floor in allowed_floors]
        return {
            "total_labeled": sum(counts.values()),
            "covered_floors": sum(1 for item in items if item["count"] > 0),
            "total_floors": len(allowed_floors),
            "items": items,
        }
