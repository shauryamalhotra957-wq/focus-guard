from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_DIR / "settings.json"


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


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    if not path.exists():
        return AppSettings()

    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(AppSettings)}
        values = {key: value for key, value in raw.items() if key in allowed}
        return AppSettings(**values).normalized()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return AppSettings()


def save_settings(
    settings: AppSettings, path: Path = DEFAULT_SETTINGS_PATH
) -> None:
    clean = settings.normalized()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(asdict(clean), indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
