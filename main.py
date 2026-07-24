"""
Entry point for the Budget Planner application.

Automatically chooses the correct database location:
- When running from source: use project folder DB
- When running as a PyInstaller EXE: use AppData DB
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

from data.database import Database
from ui.app import App
from updater import schedule_auto_update_check


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

    db_path = resolve_db_path()

    # Initialize database
    db = Database(db_path)

    # Start Tkinter app
    app = App(db)
    schedule_auto_update_check(app)
    app.mainloop()


if __name__ == "__main__":
    main()
