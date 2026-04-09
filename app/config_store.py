from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import PERSISTED_CONFIG_FIELDS, Settings, settings_to_persisted_dict


class ConfigStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_dir = Path(settings.data_dir)
        self.db_path = self.base_dir / "labels.db"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )
            connection.commit()

    def ensure_defaults(self, settings: Settings) -> None:
        values = settings_to_persisted_dict(settings)
        with sqlite3.connect(self.db_path) as connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO app_config (key, value_json)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (key, json.dumps(value)),
                )
            connection.commit()

    def load_settings(self, base_settings: Settings) -> Settings:
        self.ensure_defaults(base_settings)
        merged = base_settings.model_dump(mode="python")
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT key, value_json FROM app_config WHERE key IN (%s)" % ",".join("?" for _ in PERSISTED_CONFIG_FIELDS),
                PERSISTED_CONFIG_FIELDS,
            ).fetchall()
        for key, value_json in rows:
            merged[str(key)] = json.loads(str(value_json))
        return Settings(**merged)

    def save_settings(self, settings: Settings) -> None:
        values = settings_to_persisted_dict(settings)
        with sqlite3.connect(self.db_path) as connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO app_config (key, value_json, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE
                    SET value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value)),
                )
            connection.commit()
