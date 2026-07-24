"""
Charts page for the Budget Planner.

Displays:
- A pie chart of this month's expenses by category
- A pie chart of this month's expenses by vendor
- A 6‑month bar chart comparing income vs expenses

This page mirrors the original UI but is fully modular and powered
by the SQLite data layer.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List

import calendar as cal_mod
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ui.widgets import Card, ScrollablePage, FONT, TEXT, CARD_BG, BG, SUCCESS, DANGER
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

if TYPE_CHECKING:
    from ui.app import App


class ChartsPage(ScrollablePage):
    """
    Page for displaying financial charts.

    Includes:
    - Pie chart of current month's expenses by category
    - Pie chart of current month's expenses by vendor
    - Bar chart of last 6 months income vs expenses
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: App,
        tx_repo: TransactionRepository,
        debt_repo: DebtRepository,
        budget_repo: BudgetRepository,
        savings_service: SavingsService,
    ) -> None:
        super().__init__(parent, bg=BG)

        self.app = app
        self.tx_repo = tx_repo
        self.debt_repo = debt_repo
        self.budget_repo = budget_repo
        self.savings_service = savings_service

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = tk.Frame(self.inner, bg=BG)
        pad.pack(fill="both", expand=True, padx=28, pady=20)

        # --- Category Pie Card ---
        pie_cat_card = Card(pad, padx=16, pady=12)
        pie_cat_card.pack(fill="both", expand=True)

        tk.Label(
            pie_cat_card,
            text="Spending by Category (This Month)",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        self.fig_pie_cat = Figure(figsize=(8.2, 5.4), dpi=100)
        self.ax_pie_cat = self.fig_pie_cat.add_subplot(111)
        self.canvas_pie_cat = FigureCanvasTkAgg(self.fig_pie_cat, master=pie_cat_card)
        self.canvas_pie_cat.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))

        # --- Vendor Pie Card ---
        pie_vendor_card = Card(pad, padx=16, pady=12)
        pie_vendor_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(
            pie_vendor_card,
            text="Spending by Vendor (This Month)",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        self.fig_pie_vendor = Figure(figsize=(8.2, 5.4), dpi=100)
        self.ax_pie_vendor = self.fig_pie_vendor.add_subplot(111)
        self.canvas_pie_vendor = FigureCanvasTkAgg(self.fig_pie_vendor, master=pie_vendor_card)
        self.canvas_pie_vendor.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))

        # --- Bar Chart Card ---
        bar_card = Card(pad, padx=16, pady=12)
        bar_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(
            bar_card,
            text="Income vs Spending (Last 6 Months)",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        self.fig_bar = Figure(figsize=(6, 3), dpi=100)
        self.ax_bar = self.fig_bar.add_subplot(111)
        self.canvas_bar = FigureCanvasTkAgg(self.fig_bar, master=bar_card)
        self.canvas_bar.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))

    # ------------------------------------------------------------------
    # Refresh Logic
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh both charts using SQLite data."""

        self._refresh_pie_chart()
        self._refresh_bar_chart()

    # ------------------------------------------------------------------
    # Pie Chart
    # ------------------------------------------------------------------

    def _refresh_pie_chart(self) -> None:
        """Draw category and vendor pie charts for this month's expenses."""
        self.ax_pie_cat.clear()
        self.ax_pie_vendor.clear()

        now = datetime.today()
        summary = self.tx_repo.month_summary(now.month, now.year)
        cats = summary.get("by_cat", {})
        vendors = summary.get("by_vendor", {})

        colors = [
            "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
            "#d97706", "#16a34a", "#0d9488", "#0891b2", "#4f46e5",
            "#c026d3", "#e11d48", "#059669", "#0284c7", "#7c2d12",
        ]

        self._draw_breakdown_pie(
            ax=self.ax_pie_cat,
            title="By Category",
            breakdown=cats,
            colors=colors,
            empty_text="No expenses this month",
        )

        self._draw_breakdown_pie(
            ax=self.ax_pie_vendor,
            title="By Vendor",
            breakdown=vendors,
            colors=colors,
            empty_text="No vendor spending this month",
        )

        self.fig_pie_cat.tight_layout()
        self.fig_pie_vendor.tight_layout()
        self.canvas_pie_cat.draw()
        self.canvas_pie_vendor.draw()

    def _draw_breakdown_pie(self, ax, title: str, breakdown: dict, colors: list[str], empty_text: str) -> None:
        """Render a pie chart with in-slice percentages and a legend."""
        labels = []
        values = []

        for c, v in breakdown.items():
            if v > 0:
                labels.append(c)
                values.append(v)

        if values:
            wedges, _, _ = ax.pie(
                values,
                autopct="%1.1f%%",
                pctdistance=0.65,
                labels=None,
                colors=colors[: len(values)],
                startangle=90,
                textprops={"color": "white", "fontsize": 9, "weight": "bold"},
            )
            ax.axis("equal")
            ax.set_title(title, fontsize=10)
            ax.legend(
                wedges,
                labels,
                title="Legend",
                loc="center left",
                bbox_to_anchor=(1.0, 0.5),
                fontsize=8,
                title_fontsize=9,
                frameon=False,
            )
        else:
            ax.text(
                0.5,
                0.5,
                empty_text,
                ha="center",
                va="center",
                fontsize=10,
            )
            ax.axis("off")

    # ------------------------------------------------------------------
    # Bar Chart
    # ------------------------------------------------------------------

    def _refresh_bar_chart(self) -> None:
        """Draw the 6‑month income vs expense bar chart."""
        self.ax_bar.clear()

        today = datetime.today()
        base = today.replace(day=1)

        months: List[str] = []
        incomes: List[float] = []
        expenses: List[float] = []

        # Build last 6 months list
        month_list = []
        for i in range(5, -1, -1):
            dt = base
            for _ in range(i):
                dt = (dt.replace(day=1) - timedelta(days=1)).replace(day=1)
            month_list.append(dt)

        for dt in month_list:
            m = dt.month
            y = dt.year
            label = f"{cal_mod.month_abbr[m]} {str(y)[-2:]}"
            months.append(label)

            summary = self.tx_repo.month_summary(m, y)
            incomes.append(summary["income"])
            expenses.append(summary["expenses"])

        x = np.arange(len(months))
        width = 0.35

        self.ax_bar.bar(x - width / 2, incomes, width, label="Income", color=SUCCESS)
        self.ax_bar.bar(x + width / 2, expenses, width, label="Expenses", color=DANGER)

        self.ax_bar.set_xticks(x)
        self.ax_bar.set_xticklabels(months, rotation=30, ha="right")
        self.ax_bar.set_ylabel("Amount ($)")
        self.ax_bar.legend()

        self.fig_bar.tight_layout()
        self.canvas_bar.draw()
