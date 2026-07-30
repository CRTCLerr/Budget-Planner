"""Persistent application settings for Budget Planner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSettings:
    auto_update_check: bool = True
    auto_update_install: bool = True
    tutorial_auto_start: bool = True
    tutorial_completed: bool = False
    tutorial_last_step: int = 0


def _settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BudgetPlanner"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings() -> AppSettings:
    path = _settings_path()
    if not path.exists():
        return AppSettings()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()

    return AppSettings(
        auto_update_check=bool(payload.get("auto_update_check", True)),
        auto_update_install=bool(payload.get("auto_update_install", True)),
        tutorial_auto_start=bool(payload.get("tutorial_auto_start", True)),
        tutorial_completed=bool(payload.get("tutorial_completed", False)),
        tutorial_last_step=int(payload.get("tutorial_last_step", 0) or 0),
    )


def save_settings(settings: AppSettings) -> None:
    path = _settings_path()
    payload = {
        "auto_update_check": bool(settings.auto_update_check),
        "auto_update_install": bool(settings.auto_update_install),
        "tutorial_auto_start": bool(settings.tutorial_auto_start),
        "tutorial_completed": bool(settings.tutorial_completed),
        "tutorial_last_step": int(settings.tutorial_last_step),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
