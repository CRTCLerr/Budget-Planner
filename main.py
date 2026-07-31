"""
Entry point for the Budget Planner application.

Automatically chooses the correct database location:
- When running from source: use project folder DB
- When running as a PyInstaller EXE: use AppData DB
"""

from __future__ import annotations

import sys
import os
import subprocess
import shutil
from pathlib import Path

from core.app_settings import load_settings
from data.database import Database
from ui.app import App
from core.updater import notify_post_update_status, schedule_auto_update_check
from ui.tutorial import TutorialController


def ensure_managed_runtime_location() -> bool:
    """Redirect packaged Windows runs to a stable LocalAppData runtime path.

    This prevents legacy shortcuts/old install folders from pinning users
    to outdated binaries. If the managed runtime exists, we launch it and
    exit the current process. If it does not exist yet, we seed it once.
    """

    if not getattr(sys, "frozen", False):
        return True
    if not sys.platform.startswith("win"):
        return True

    current_exe = Path(sys.executable).resolve()
    runtime_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BudgetPlanner" / "runtime"
    managed_exe = runtime_dir / "BudgetPlanner.exe"

    # Already running from managed location.
    if current_exe == managed_exe:
        return True

    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)

        # Seed managed runtime only if missing; never overwrite to avoid
        # downgrading when launched from an old legacy shortcut.
        if not managed_exe.exists():
            shutil.copy2(current_exe, managed_exe)

        creation_flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creation_flags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [str(managed_exe)],
            creationflags=creation_flags,
            close_fds=True,
        )
        return False
    except Exception:
        # If migration fails for any reason, continue with current executable.
        return True


def resolve_db_path() -> str:
    """
    Determine the correct database path depending on environment.
    """

    if getattr(sys, "frozen", False):
        # Running as a PyInstaller EXE
        appdata = Path(os.environ["LOCALAPPDATA"]) / "BudgetPlanner"
        appdata.mkdir(parents=True, exist_ok=True)
        return str(appdata / "budget_data.db")

    else:
        # Running from source (development)
        base_dir = Path(__file__).resolve().parent
        return str(base_dir / "budget_data.db")


def main() -> None:
    """Application bootstrap."""

    if not ensure_managed_runtime_location():
        return

    db_path = resolve_db_path()
    settings = load_settings()

    # Initialize database
    db = Database(db_path)

    # Start Tkinter app
    app = App(db, settings)
    app.tutorial_controller = TutorialController(app, settings)
    app.after(500, lambda: notify_post_update_status(app))
    if settings.auto_update_check:
        schedule_auto_update_check(app)
    # Fire tutorial startup checks more than once to survive heavy startup UI work.
    app.after_idle(app.tutorial_controller.start_if_needed)
    app.after(900, app.tutorial_controller.start_if_needed)
    app.after(1800, app.tutorial_controller.start_if_needed)
    app.mainloop()


if __name__ == "__main__":
    main()
