"""Settings page for application preferences."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from app_settings import save_settings
from updater import check_for_updates
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

        tk.Button(
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
        ).pack(anchor="w")

    def _save_auto_update_setting(self) -> None:
        self.app.settings.auto_update_check = bool(self.var_auto_update.get())
        self.app.settings.auto_update_install = bool(self.var_auto_install.get())
        save_settings(self.app.settings)
