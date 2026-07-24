"""Persistent application settings for Budget Planner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSettings:
    auto_update_check: bool = True


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

    return AppSettings(auto_update_check=bool(payload.get("auto_update_check", True)))


def save_settings(settings: AppSettings) -> None:
    path = _settings_path()
    payload = {
        "auto_update_check": bool(settings.auto_update_check),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
