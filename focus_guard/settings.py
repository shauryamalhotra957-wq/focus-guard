from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
LEGACY_SETTINGS_PATH = PROJECT_DIR / "settings.json"
SETTINGS_DIRECTORY_NAME = "Focus Guard"


def get_default_settings_path(
    *,
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return the per-user settings path, retaining the old path elsewhere."""
    platform_name = sys.platform if platform is None else platform
    environment_values = os.environ if environment is None else environment
    local_app_data = environment_values.get("LOCALAPPDATA", "").strip()

    if platform_name == "win32" and local_app_data:
        return (
            Path(local_app_data)
            / SETTINGS_DIRECTORY_NAME
            / "settings.json"
        )

    return LEGACY_SETTINGS_PATH


DEFAULT_SETTINGS_PATH = get_default_settings_path()


@dataclass
class AppSettings:
    camera_index: int = 0
    song_path: str = ""
    model_name: str = "yolo26n.pt"
    confidence: float = 0.45
    trigger_seconds: float = 6.0
    clear_seconds: float = 3.0
    cooldown_seconds: float = 60.0
    inference_fps: float = 3.0
    volume: float = 0.80
    ignore_bottom_percent: float = 18.0
    require_person: bool = True

    def normalized(self) -> "AppSettings":
        return AppSettings(
            camera_index=max(0, int(self.camera_index)),
            song_path=str(self.song_path).strip(),
            model_name=str(self.model_name).strip() or "yolo26n.pt",
            confidence=min(0.95, max(0.10, float(self.confidence))),
            trigger_seconds=min(120.0, max(1.0, float(self.trigger_seconds))),
            clear_seconds=min(30.0, max(0.5, float(self.clear_seconds))),
            cooldown_seconds=min(3600.0, max(0.0, float(self.cooldown_seconds))),
            inference_fps=min(10.0, max(1.0, float(self.inference_fps))),
            volume=min(1.0, max(0.0, float(self.volume))),
            ignore_bottom_percent=min(
                60.0, max(0.0, float(self.ignore_bottom_percent))
            ),
            require_person=bool(self.require_person),
        )


def _read_settings(path: Path) -> AppSettings | None:
    """Read a valid settings file, or return ``None`` when it is unusable."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        allowed = {field.name for field in fields(AppSettings)}
        values = {key: value for key, value in raw.items() if key in allowed}
        return AppSettings(**values).normalized()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def load_settings(path: Path | None = None) -> AppSettings:
    target_path = DEFAULT_SETTINGS_PATH if path is None else Path(path)

    if target_path.exists():
        return _read_settings(target_path) or AppSettings()

    should_migrate_legacy = (
        path is None
        and target_path != LEGACY_SETTINGS_PATH
        and LEGACY_SETTINGS_PATH.exists()
    )
    if not should_migrate_legacy:
        return AppSettings()

    legacy_settings = _read_settings(LEGACY_SETTINGS_PATH)
    if legacy_settings is None:
        return AppSettings()

    try:
        save_settings(legacy_settings, target_path)
    except OSError:
        # A read-only or unavailable app-data directory must not discard the
        # user's existing settings. Keep using the legacy values for this run.
        pass
    return legacy_settings


def save_settings(
    settings: AppSettings, path: Path | None = None
) -> None:
    target_path = DEFAULT_SETTINGS_PATH if path is None else Path(path)
    clean = settings.normalized()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(asdict(clean), indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target_path)
