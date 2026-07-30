"""Settings page for application preferences."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING

from core.app_settings import save_settings
from core.updater import check_for_updates
from ui.widgets import BG, CARD_BG, FONT, TEXT, TEXT_SEC, BORDER, ScrollablePage

if TYPE_CHECKING:
    from ui.app import App


class SettingsPage(ScrollablePage):
    """Settings UI with updater-related preferences."""

    def __init__(
        self,
        parent: tk.Widget,
        app: "App",
        tx_repo,
        debt_repo,
        budget_repo,
        savings_service,
    ) -> None:
        super().__init__(parent, bg=BG)
        self.app = app

        self.var_auto_update = tk.BooleanVar(value=bool(self.app.settings.auto_update_check))
        self.var_auto_install = tk.BooleanVar(value=bool(self.app.settings.auto_update_install))
        self._build_ui()

    def _build_ui(self) -> None:
        container = tk.Frame(self.inner, bg=BG)
        container.pack(fill="both", expand=True, padx=28, pady=20)

        card = tk.Frame(
            container,
            bg=CARD_BG,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        card.pack(fill="x")
        self.update_card = card

        tk.Label(
            card,
            text="Updates",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            card,
            text=(
                "Check GitHub releases for new versions. "
                "You will be notified, the update can download in-app, and the app will restart after apply."
            ),
            font=(FONT, 10),
            fg=TEXT_SEC,
            bg=CARD_BG,
            justify="left",
            wraplength=700,
        ).pack(anchor="w", pady=(0, 12))

        tk.Checkbutton(
            card,
            text="Check for updates automatically at startup",
            variable=self.var_auto_update,
            onvalue=True,
            offvalue=False,
            command=self._save_auto_update_setting,
            font=(FONT, 10),
            fg=TEXT,
            bg=CARD_BG,
            activebackground=CARD_BG,
            selectcolor=CARD_BG,
        ).pack(anchor="w", pady=(0, 14))

        tk.Checkbutton(
            card,
            text="Auto-install updates after confirmation",
            variable=self.var_auto_install,
            onvalue=True,
            offvalue=False,
            command=self._save_auto_update_setting,
            font=(FONT, 10),
            fg=TEXT,
            bg=CARD_BG,
            activebackground=CARD_BG,
            selectcolor=CARD_BG,
        ).pack(anchor="w", pady=(0, 14))

        self.btn_check_updates = tk.Button(
            card,
            text="Check for Updates Now",
            font=(FONT, 10, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=lambda: check_for_updates(self.app, prompt_if_latest=True),
        )
        self.btn_check_updates.pack(anchor="w")

        tutorial_card = tk.Frame(
            container,
            bg=CARD_BG,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        tutorial_card.pack(fill="x", pady=(16, 0))
        self.tutorial_card = tutorial_card

        tk.Label(
            tutorial_card,
            text="Tutorial",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            tutorial_card,
            text=(
                "Use the guided tutorial to learn each screen step by step. "
                "It can start automatically once, and you can replay it any time."
            ),
            font=(FONT, 10),
            fg=TEXT_SEC,
            bg=CARD_BG,
            justify="left",
            wraplength=700,
        ).pack(anchor="w", pady=(0, 12))

        self.var_tutorial_auto_start = tk.BooleanVar(value=bool(self.app.settings.tutorial_auto_start))

        self.chk_tutorial_auto_start = tk.Checkbutton(
            tutorial_card,
            text="Show tutorial on startup",
            variable=self.var_tutorial_auto_start,
            onvalue=True,
            offvalue=False,
            command=self._save_tutorial_setting,
            font=(FONT, 10),
            fg=TEXT,
            bg=CARD_BG,
            activebackground=CARD_BG,
            selectcolor=CARD_BG,
        )
        self.chk_tutorial_auto_start.pack(anchor="w", pady=(0, 12))

        btn_row = tk.Frame(tutorial_card, bg=CARD_BG)
        btn_row.pack(anchor="w")

        self.btn_start_tutorial = tk.Button(
            btn_row,
            text="Start Tutorial",
            font=(FONT, 10, "bold"),
            bg="#0f766e",
            fg="#ffffff",
            activebackground="#115e59",
            activeforeground="#ffffff",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._start_tutorial,
        )
        self.btn_start_tutorial.pack(side="left")

        self.btn_reset_tutorial = tk.Button(
            btn_row,
            text="Reset Tutorial Completion",
            font=(FONT, 10, "bold"),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            activeforeground="#111827",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._reset_tutorial_completion,
        )
        self.btn_reset_tutorial.pack(side="left", padx=(10, 0))

    def _save_auto_update_setting(self) -> None:
        self.app.settings.auto_update_check = bool(self.var_auto_update.get())
        self.app.settings.auto_update_install = bool(self.var_auto_install.get())
        save_settings(self.app.settings)

    def _save_tutorial_setting(self) -> None:
        self.app.settings.tutorial_auto_start = bool(self.var_tutorial_auto_start.get())
        save_settings(self.app.settings)

    def _start_tutorial(self) -> None:
        controller = getattr(self.app, "tutorial_controller", None)
        if controller is not None:
            controller.restart()
            return

        messagebox.showerror(
            "Tutorial Unavailable",
            "The tutorial controller was not initialized. Restart the app and try again.",
        )

    def _reset_tutorial_completion(self) -> None:
        self.app.settings.tutorial_completed = False
        self.app.settings.tutorial_last_step = 0
        save_settings(self.app.settings)
