from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.backup import create_backup_snapshot, find_latest_backup_by_label, read_backup_manifest, restore_backup_snapshot
from app.paths import INTRO_DISABLED_SUFFIX, MODS_ROOT, iter_disabled_intro_videos, iter_intro_video_candidates


@dataclass(frozen=True)
class ModEntry:
    name: str
    path: Path
    install_files: tuple[Path, ...]
    readme_path: Path | None

    @property
    def backup_label(self) -> str:
        return f"mod_{self.name}"


def list_mods() -> list[ModEntry]:
    if not MODS_ROOT.is_dir():
        return []

    mods: list[ModEntry] = []
    for mod_dir in sorted([path for path in MODS_ROOT.iterdir() if path.is_dir()]):
        install_files = tuple(_iter_install_files(mod_dir))
        if not install_files:
            continue

        readme_path = next(iter(sorted(mod_dir.glob("README*"))), None)
        mods.append(
            ModEntry(
                name=mod_dir.name,
                path=mod_dir,
                install_files=install_files,
                readme_path=readme_path,
            )
        )
    return mods


def _iter_install_files(mod_dir: Path) -> list[Path]:
    install_files: list[Path] = []
    for file_path in mod_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.parent == mod_dir and file_path.name.lower().startswith("readme"):
            continue
        install_files.append(file_path)
    return sorted(install_files)


def _relative_install_path(mod: ModEntry, source: Path) -> Path:
    return source.relative_to(mod.path)


def iter_managed_install_targets(install_path: Path, mods: list[ModEntry]) -> list[Path]:
    targets: list[Path] = []
    seen: set[Path] = set()
    for mod in mods:
        for source in mod.install_files:
            target = install_path / _relative_install_path(mod, source)
            if target not in seen:
                targets.append(target)
                seen.add(target)
    return targets


def create_baseline_backup(install_path: Path, mods: list[ModEntry]) -> tuple[int, Path]:
    targets = iter_managed_install_targets(install_path, mods)
    backup_dir = create_backup_snapshot(install_path, targets, "baseline")
    existing_count = sum(1 for target in targets if target.exists())
    return existing_count, backup_dir


def install_mod(install_path: Path, mod: ModEntry) -> tuple[int, Path]:
    target_files = [install_path / _relative_install_path(mod, source) for source in mod.install_files]
    backup_dir = create_backup_snapshot(install_path, target_files, mod.backup_label)

    copied_files = 0
    for source in mod.install_files:
        relative_path = _relative_install_path(mod, source)
        destination = install_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_files += 1

    return copied_files, backup_dir


def disable_intro_videos(install_path: Path) -> tuple[int, Path | None]:
    intro_files = iter_intro_video_candidates(install_path)
    active_files = [path for path in intro_files if not path.name.endswith(INTRO_DISABLED_SUFFIX)]
    if not active_files:
        return 0, None

    backup_dir = create_backup_snapshot(install_path, active_files, "intro_videos")

    changed = 0
    for source in active_files:
        source.rename(source.with_name(source.name + INTRO_DISABLED_SUFFIX))
        changed += 1

    return changed, backup_dir


def restore_intro_videos(install_path: Path) -> int:
    disabled_files = iter_disabled_intro_videos(install_path)
    changed = 0
    for source in disabled_files:
        restored_name = source.name[: -len(INTRO_DISABLED_SUFFIX)]
        source.rename(source.with_name(restored_name))
        changed += 1
    return changed


def find_mod_backup(install_path: Path, mod: ModEntry) -> Path | None:
    return find_latest_backup_by_label(install_path, mod.backup_label)


def get_uninstallable_new_files(install_path: Path, mod: ModEntry, snapshot_dir: Path) -> list[Path]:
    _, records = read_backup_manifest(snapshot_dir)
    record_by_relative = {record.relative_path: record for record in records}
    extra_files: list[Path] = []

    for source in mod.install_files:
        relative_path = _relative_install_path(mod, source).as_posix()
        record = record_by_relative.get(relative_path)
        if record is None or record.existed:
            continue
        installed_file = install_path / relative_path
        if installed_file.exists():
            extra_files.append(installed_file)

    return sorted(extra_files)


def remove_paths(paths: list[Path]) -> int:
    removed = 0
    for path in sorted(paths, key=lambda entry: len(entry.parts), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1

    parent_dirs = {parent for path in paths for parent in path.parents}
    for directory in sorted(parent_dirs, key=lambda entry: len(entry.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            continue

    return removed


def uninstall_mod(install_path: Path, mod: ModEntry, remove_added_files: bool) -> tuple[int, int, Path]:
    snapshot_dir = find_mod_backup(install_path, mod)
    if snapshot_dir is None:
        raise FileNotFoundError(f"No backup found for {mod.name}")

    restored_files = restore_backup_snapshot(install_path, snapshot_dir)
    removed_files = 0
    if remove_added_files:
        removable_files = get_uninstallable_new_files(install_path, mod, snapshot_dir)
        removed_files = remove_paths(removable_files)

    return restored_files, removed_files, snapshot_dir
