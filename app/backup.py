from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import tempfile
import zipfile


class BackupManager:
    def __init__(self, data_dir: str) -> None:
        self.base_dir = Path(data_dir)

    def export_zip(self) -> bytes:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.base_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(self.base_dir)))
        buffer.seek(0)
        return buffer.getvalue()

    def import_zip(self, payload: bytes) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="elevator-backup-") as tmp_dir:
            temp_root = Path(tmp_dir)
            extract_root = temp_root / "extract"
            extract_root.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(BytesIO(payload)) as archive:
                    for member in archive.infolist():
                        member_path = Path(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise ValueError("invalid archive path")
                    archive.extractall(extract_root)
            except zipfile.BadZipFile as exc:
                raise ValueError("invalid backup archive") from exc

            for child in list(self.base_dir.iterdir()):
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

            for child in extract_root.iterdir():
                target = self.base_dir / child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                else:
                    shutil.copy2(child, target)
