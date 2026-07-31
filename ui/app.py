"""
Main Tkinter application class for the Budget Planner.

This module:
- Creates the main window
- Builds the sidebar and header
- Loads all page frames
- Manages navigation between pages
- Provides shared repositories/services to all pages

This is the central UI controller, replacing the old monolithic App class.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import tkinter as tk
from datetime import datetime
from typing import Dict, Type

from core.app_settings import AppSettings
from data.database import Database
from data.categories import CategoryRepository
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

from ui.widgets import (
    SIDEBAR_BG,
    CARD_BG,
    BORDER,
    TEXT,
    TEXT_SEC,
    FONT,
    SidebarButton,
)

# Page modules (imported later to avoid circular imports)
from ui.dashboard import DashboardPage
from ui.add_transaction import AddTransactionPage
from ui.history import HistoryPage
from ui.budgets import BudgetsPage
from ui.charts import ChartsPage
from ui.debt import DebtPage
from ui.savings import SavingsPage
from ui.settings import SettingsPage


class _TutorialControllerProtocol:
    def start_if_needed(self) -> None:
        raise NotImplementedError


class App(tk.Tk):
    """
    Root Tkinter application window.

    Responsibilities:
    - Initialize repositories/services
    - Build sidebar + header
    - Create and store all page frames
    - Handle navigation
    """

    def __init__(self, db: Database, settings: AppSettings) -> None:
        super().__init__()

        # Window configuration
        self.title("Budget Planner")
        self._load_icon()
        self.geometry("1160x740")
        self.minsize(960, 600)
        self.configure(bg="#f1f5f9")

        # --- Data Layer -------------------------------------------------------
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.debt_repo = DebtRepository(db)
        self.budget_repo = BudgetRepository(db)
        self.savings_service = SavingsService(self.tx_repo)
        self.settings = settings
        self.tutorial_controller: _TutorialControllerProtocol | None = None

        # --- UI Containers ----------------------------------------------------
        self.sidebar: tk.Frame
        self.header_bar: tk.Frame
        self.header_title: tk.Label
        self.header_date: tk.Label
        self.content_wrapper: tk.Frame

        # Page storage
        self.pages: Dict[str, tk.Frame] = {}
        self.nav_buttons: Dict[str, SidebarButton] = {}
        self.current_page: str = ""
        self._active_mousewheel_page: tk.Frame | None = None

        # Build UI
        self._build_sidebar()
        self._build_header()
        self._build_content_wrapper()
        self._load_pages()

        # Default page
        self.navigate("Dashboard")

    def _load_icon(self):
        """Load the window icon correctly in both dev and PyInstaller EXE."""
        if getattr(sys, 'frozen', False):
            # Running as EXE
            base_path = Path(sys._MEIPASS)
        else:
            # Running from source
            base_path = Path(__file__).resolve().parent.parent  # project root

        icon_path = base_path / "assets" / "moneylogo.ico"

        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception as e:
                print("Failed to load icon:", e)


    # ----------------------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------------------

    def _build_sidebar(self) -> None:
        """Build the left sidebar with navigation buttons."""
        self.sidebar = tk.Frame(self, bg=SIDEBAR_BG, width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Brand
        brand = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        brand.pack(fill="x", pady=(24, 28))

        tk.Label(
            brand,
            text="💰",
            font=(FONT, 22),
            bg=SIDEBAR_BG,
            fg="#ffffff",
        ).pack(side="left", padx=(20, 8))

        tk.Label(
            brand,
            text="Budget\nPlanner",
            font=(FONT, 14, "bold"),
            bg=SIDEBAR_BG,
            fg="#ffffff",
            justify="left",
        ).pack(side="left")

        tk.Frame(self.sidebar, bg="#334155", height=1).pack(
            fill="x", padx=16, pady=(0, 12)
        )

        # Navigation items
        nav_items = [
            ("📊", "Dashboard"),
            ("➕", "Add Transaction"),
            ("💳", "Debt"),
            ("📋", "History"),
            ("🎯", "Budget Limits"),
            ("📈", "Charts"),
            ("💸", "Savings"),
            ("⚙️", "Settings"),
        ]

        for icon, label in nav_items:
            btn = SidebarButton(
                self.sidebar,
                icon=icon,
                label=label,
                command=lambda l=label: self.navigate(l),
            )
            btn.pack(fill="x", ipady=8, pady=2)
            self.nav_buttons[label] = btn

        # Footer
        tk.Frame(self.sidebar, bg=SIDEBAR_BG).pack(fill="both", expand=True)
        tk.Label(
            self.sidebar,
            text="Data stored in SQLite",
            font=(FONT, 8),
            fg="#475569",
            bg=SIDEBAR_BG,
            justify="center",
        ).pack(pady=(0, 16))

    # ----------------------------------------------------------------------
    # Header
    # ----------------------------------------------------------------------

    def _build_header(self) -> None:
        """Build the top header bar."""
        self.header_bar = tk.Frame(
            self,
            bg=CARD_BG,
            height=56,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.header_bar.pack(side="top", fill="x")
        self.header_bar.pack_propagate(False)

        self.header_title = tk.Label(
            self.header_bar,
            text="Dashboard",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        )
        self.header_title.pack(side="left", padx=24)

        self.header_date = tk.Label(
            self.header_bar,
            text=datetime.today().strftime("%A, %B %d, %Y"),
            font=(FONT, 10),
            fg=TEXT_SEC,
            bg=CARD_BG,
        )
        self.header_date.pack(side="right", padx=24)

    # ----------------------------------------------------------------------
    # Content Wrapper
    # ----------------------------------------------------------------------

    def _build_content_wrapper(self) -> None:
        """Create the container where pages will be displayed."""
        self.content_wrapper = tk.Frame(self, bg="#f1f5f9")
        self.content_wrapper.pack(side="left", fill="both", expand=True)

    # ----------------------------------------------------------------------
    # Page Loading
    # ----------------------------------------------------------------------

    def _load_pages(self) -> None:
        """Instantiate all page frames and store them."""
        page_classes: Dict[str, Type[tk.Frame]] = {
            "Dashboard": DashboardPage,
            "Add Transaction": AddTransactionPage,
            "History": HistoryPage,
            "Budget Limits": BudgetsPage,
            "Charts": ChartsPage,
            "Debt": DebtPage,
            "Savings": SavingsPage,
            "Settings": SettingsPage,
        }

        for name, cls in page_classes.items():
            frame = cls(
                parent=self.content_wrapper,
                app=self,
                tx_repo=self.tx_repo,
                debt_repo=self.debt_repo,
                budget_repo=self.budget_repo,
                savings_service=self.savings_service,
            )
            self.pages[name] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            
    # ----------------------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------------------

    def navigate(self, page_name: str) -> None:
        """Switch to the given page."""
        if page_name not in self.pages:
            return

        # Hide ALL pages first and deactivate any active wheel binding
        if self._active_mousewheel_page is not None:
            if hasattr(self._active_mousewheel_page, "deactivate_mousewheel"):
                self._active_mousewheel_page.deactivate_mousewheel()
            self._active_mousewheel_page = None

        for frame in self.pages.values():
            frame.place_forget()

        # Show new page
        frame = self.pages[page_name]
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.current_page = page_name

        if hasattr(frame, "activate_mousewheel"):
            frame.activate_mousewheel()
            self._active_mousewheel_page = frame

        # Update header
        self.header_title.configure(text=page_name)

        # Update sidebar active state
        for name, btn in self.nav_buttons.items():
            btn.set_active(name == page_name)

        # Refresh page if it has a refresh() method
        if hasattr(frame, "refresh"):
            frame.refresh()

    # ----------------------------------------------------------------------
    # Global Refresh Helpers
    # ----------------------------------------------------------------------

    def refresh_all(self) -> None:
        """Refresh all pages that implement refresh()."""
        for frame in self.pages.values():
            if hasattr(frame, "refresh"):
                frame.refresh()
