from __future__ import annotations

from pathlib import Path


DEFAULT_STEAM_INSTALL = (
    Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common" / "ForzaHorizon6"
)
APP_ROOT = Path(__file__).resolve().parent.parent
MODS_ROOT = APP_ROOT / "mods"
BACKUP_ROOT_NAME = ".fh6_mod_manager_backups"
INTRO_DISABLED_SUFFIX = ".fh6mm.disabled"

INTRO_VIDEO_LOCATIONS = (
    "media/movies",
    "media/videos",
    "movies",
    "videos",
)
INTRO_VIDEO_NAMES = (
    "Turn10_Logo.bk2",
    "MicrosoftStudios_Logo.bk2",
    "XboxGamesStudios_Logo.bk2",
    "PlaygroundGames_Logo.bk2",
    "Intro.bk2",
    "Startup_Sequence.bk2",
)


def detect_install_path() -> Path | None:
    if DEFAULT_STEAM_INSTALL.is_dir():
        return DEFAULT_STEAM_INSTALL
    return None


def normalize_install_path(path_text: str) -> Path:
    return Path(path_text).expanduser().resolve()


def get_backup_root(install_path: Path) -> Path:
    return install_path / BACKUP_ROOT_NAME


def iter_intro_video_candidates(install_path: Path) -> list[Path]:
    candidates: list[Path] = []

    for relative_dir in INTRO_VIDEO_LOCATIONS:
        base_dir = install_path / relative_dir
        if not base_dir.is_dir():
            continue

        for name in INTRO_VIDEO_NAMES:
            candidate = base_dir / name
            if candidate.is_file():
                candidates.append(candidate)

        if candidates:
            return candidates

    for relative_dir in INTRO_VIDEO_LOCATIONS:
        base_dir = install_path / relative_dir
        if not base_dir.is_dir():
            continue

        for file_path in base_dir.rglob("*.bk2"):
            lowered = file_path.name.lower()
            if "intro" in lowered or "logo" in lowered or "startup" in lowered:
                candidates.append(file_path)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)

    return unique_candidates


def iter_disabled_intro_videos(install_path: Path) -> list[Path]:
    disabled: list[Path] = []
    for relative_dir in INTRO_VIDEO_LOCATIONS:
        base_dir = install_path / relative_dir
        if not base_dir.is_dir():
            continue
        disabled.extend(base_dir.rglob(f"*{INTRO_DISABLED_SUFFIX}"))
    return sorted(disabled)
