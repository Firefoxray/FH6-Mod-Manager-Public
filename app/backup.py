from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.paths import get_backup_root


@dataclass(frozen=True)
class BackupRecord:
    relative_path: str
    existed: bool


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _display_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _default_display_name(label: str) -> str:
    timestamp = _display_timestamp()
    if label == "baseline":
        return f"Current-State Backup - {timestamp}"
    if label == "intro_videos":
        return f"Intro Videos Backup - {timestamp}"
    if label.startswith("mod_"):
        return f"Before installing {label[4:]} - {timestamp}"
    return f"{label or 'Backup'} - {timestamp}"


def create_backup_snapshot(
    install_path: Path,
    files_to_backup: list[Path],
    label: str,
    display_name: str | None = None,
    notes: str | None = None,
) -> Path:
    backup_root = get_backup_root(install_path)
    snapshot_dir = backup_root / f"{_timestamp()}_{label}"
    payload_dir = snapshot_dir / "files"
    payload_dir.mkdir(parents=True, exist_ok=False)

    manifest: list[dict[str, str | bool]] = []
    seen: set[Path] = set()
    for source in files_to_backup:
        if source in seen:
            continue
        seen.add(source)

        relative_path = source.relative_to(install_path)
        existed = source.exists()
        if existed:
            destination = payload_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        manifest.append({"relative_path": relative_path.as_posix(), "existed": existed})

    payload: dict[str, object] = {
        "label": label,
        "display_name": display_name or _default_display_name(label),
        "files": manifest,
    }
    if notes:
        payload["notes"] = notes

    (snapshot_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return snapshot_dir


def list_backups(install_path: Path) -> list[Path]:
    backup_root = get_backup_root(install_path)
    if not backup_root.is_dir():
        return []
    return sorted([path for path in backup_root.iterdir() if path.is_dir()], reverse=True)


def read_backup_manifest(snapshot_dir: Path) -> tuple[str, list[BackupRecord]]:
    manifest_path = snapshot_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    label = str(payload.get("label", ""))
    records = [
        BackupRecord(
            relative_path=str(entry["relative_path"]),
            existed=bool(entry.get("existed", True)),
        )
        for entry in payload.get("files", [])
    ]
    return label, records


def read_backup_display_name(snapshot_dir: Path) -> str:
    manifest_path = snapshot_dir / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    display_name = payload.get("display_name", "")
    if not isinstance(display_name, str):
        return ""
    return display_name.strip()


def update_backup_display_name(snapshot_dir: Path, display_name: str) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    payload: dict[str, object]
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}

    payload = loaded if isinstance(loaded, dict) else {}
    cleaned_name = display_name.strip()
    if cleaned_name:
        payload["display_name"] = cleaned_name
    else:
        payload.pop("display_name", None)
    payload.setdefault("label", "")
    payload.setdefault("files", [])
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def find_latest_backup_by_label(install_path: Path, label: str) -> Path | None:
    for snapshot_dir in list_backups(install_path):
        snapshot_label, _ = read_backup_manifest(snapshot_dir)
        if snapshot_label == label:
            return snapshot_dir
    return None


def restore_backup_snapshot(install_path: Path, snapshot_dir: Path) -> int:
    payload_dir = snapshot_dir / "files"

    restored_files = 0
    _, records = read_backup_manifest(snapshot_dir)
    for record in records:
        if not record.existed:
            continue
        source = payload_dir / record.relative_path
        if not source.is_file():
            raise FileNotFoundError(f"Backup payload is missing: {source}")
        destination = install_path / record.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        restored_files += 1
    return restored_files
