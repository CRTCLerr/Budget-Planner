"""
Savings page for the Budget Planner.

Displays:
- Combined Savings + E‑Savings graph over time
- Trendlines for both buckets
- Savings forecast (advisor-aware, with fallback)
- Table of all savings-related transactions
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
from datetime import datetime, date

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ui.widgets import Card, ScrollablePage, FONT, TEXT, TEXT_SEC, CARD_BG, BG, PRIMARY, SUCCESS
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService, SAVINGS_BUCKETS

if TYPE_CHECKING:
    from ui.app import App


class SavingsPage(ScrollablePage):
    """
    Page showing savings analytics and savings-related transactions.

    Features:
    - Combined Savings + E‑Savings line graph
    - Trendlines for both buckets
    - Savings forecast (advisor-aware, with fallback)
    - Table of all savings transactions
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

        # --- Forecast Card ---
        forecast_card = Card(pad, padx=16, pady=12)
        forecast_card.pack(fill="x", expand=False, pady=(0, 12))

        tk.Label(
            forecast_card,
            text="Savings Forecast",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        self.forecast_text = tk.Text(
            forecast_card,
            height=10,
            font=(FONT, 10),
            bg=CARD_BG,
            fg=TEXT_SEC,
            relief="flat",
            wrap="word",
        )
        self.forecast_text.pack(fill="both", expand=True, pady=(8, 0))
        self.forecast_text.configure(state="disabled")

        # --- Graph Card ---
        graph_card = Card(pad, padx=16, pady=12)
        graph_card.pack(fill="both", expand=True)

        tk.Label(
            graph_card,
            text="Savings Over Time",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_card)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(8, 0))

        # --- Table Card ---
        table_card = Card(pad, padx=16, pady=12)
        table_card.pack(fill="both", expand=True, pady=(12, 0))

        tk.Label(
            table_card,
            text="Savings Transactions",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        cols = ("date", "bucket", "direction", "amount", "category", "description")
        self.tree = ttk.Treeview(table_card, columns=cols, show="headings", height=12)

        for c, w, a in [
            ("date", 100, "w"),
            ("bucket", 100, "center"),
            ("direction", 120, "center"),
            ("amount", 110, "e"),
            ("category", 120, "w"),
            ("description", 260, "w"),
        ]:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor=a)

        table_scroll = tk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=table_scroll.set)
        table_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, pady=(8, 0))

    # ------------------------------------------------------------------
    # Refresh Logic
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh the forecast, graph, and table."""
        self._refresh_forecast()
        self._refresh_graph()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Forecast Helpers
    # ------------------------------------------------------------------

    def _estimate_monthly_savings_from_history(self) -> float:
        """Estimate monthly savings from actual 'To Savings' transactions."""
        rows = self.savings_service.savings_transactions_table()
        if not rows:
            return 0.0

        monthly_totals = {}
        for date_s, bucket, direction, amount, category, desc in rows:
            if direction != "To Savings":
                continue
            try:
                dt = datetime.strptime(date_s, "%Y-%m-%d").date()
            except Exception:
                continue
            key = f"{dt.year:04d}-{dt.month:02d}"
            monthly_totals.setdefault(key, 0.0)
            monthly_totals[key] += amount

        if not monthly_totals:
            return 0.0

        return sum(monthly_totals.values()) / len(monthly_totals)

    def _simple_forecast(self, monthly_savings: float) -> dict:
        """Simple fallback forecast when advisor is unavailable."""
        try:
            current_savings = self.savings_service.total_savings()
        except Exception:
            current_savings = 0.0

        monthly_expenses = 2000.0  # fallback baseline

        milestones = {
            "Emergency Fund ($1,000)": 1000,
            "1 Month of Expenses": monthly_expenses,
            "3 Months of Expenses": monthly_expenses * 3,
            "6 Months of Expenses": monthly_expenses * 6,
        }

        results = {}
        today = datetime.today().date()

        for label, target in milestones.items():
            if monthly_savings <= 0:
                results[label] = "No progress (monthly savings is $0)"
                continue

            if current_savings >= target:
                results[label] = "Already achieved"
                continue

            remaining = target - current_savings
            months_needed = max(1, int(remaining / monthly_savings + 0.999))

            year = today.year + (today.month + months_needed - 1) // 12
            month = (today.month + months_needed - 1) % 12 + 1
            target_date = date(year, month, 1)

            results[label] = f"Reached by {target_date.strftime('%Y-%m')}"

        # Add 12‑month and 24‑month projections
        results["Projected Savings in 12 Months"] = f"${current_savings + monthly_savings * 12:,.2f}"
        results["Projected Savings in 24 Months"] = f"${current_savings + monthly_savings * 24:,.2f}"

        return results

    # ------------------------------------------------------------------
    # Forecast
    # ------------------------------------------------------------------

    def _refresh_forecast(self) -> None:
        """Populate the Savings Forecast card using advisor logic, with fallback."""
        advisor = getattr(self.app, "advisor", None)
        forecast = {}

        if advisor is not None:
            try:
                data = advisor._analyze_spending()
                avg_history = data["avg_history"]

                try:
                    rec = advisor.generate_recommendation()
                except Exception:
                    rec = advisor._strategy_balanced(data)

                monthly_savings = rec.savings_target

                forecast = advisor._forecast_savings(
                    monthly_savings=monthly_savings,
                    avg_history=avg_history,
                )

                # Add 12‑month and 24‑month projections
                current_savings = self.savings_service.total_savings()
                forecast["Projected Savings in 12 Months"] = f"${current_savings + monthly_savings * 12:,.2f}"
                forecast["Projected Savings in 24 Months"] = f"${current_savings + monthly_savings * 24:,.2f}"

            except Exception:
                forecast = {}

        # Fallback if advisor unavailable or failed
        if not forecast:
            monthly_savings = self._estimate_monthly_savings_from_history()
            forecast = self._simple_forecast(monthly_savings)

        # Update UI
        self.forecast_text.configure(state="normal")
        self.forecast_text.delete("1.0", "end")

        for label, msg in forecast.items():
            self.forecast_text.insert("end", f"• {label}: {msg}\n")

        self.forecast_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def _refresh_graph(self) -> None:
        """Draw the combined Savings + E‑Savings graph with trendlines."""
        self.ax.clear()

        history = self.savings_service.history_points()
        if not history:
            self.ax.text(
                0.5,
                0.5,
                "No savings activity yet",
                ha="center",
                va="center",
                fontsize=10,
            )
            self.canvas.draw()
            return

        dates = list(history.keys())
        x = np.arange(len(dates))

        bucket_values = {b: [] for b in SAVINGS_BUCKETS}
        for d in dates:
            for b in SAVINGS_BUCKETS:
                bucket_values[b].append(history[d].get(b, 0.0))

        colors = {
            "Savings": SUCCESS,
            "E-Savings": PRIMARY,
        }

        for b in SAVINGS_BUCKETS:
            y = bucket_values[b]
            self.ax.plot(x, y, label=b, linewidth=2, color=colors[b])

            if len(x) >= 2:
                xs = x.astype(float)
                coef = np.polyfit(xs, y, 1)
                trend = np.poly1d(coef)(xs)
                self.ax.plot(
                    x,
                    trend,
                    linestyle="--",
                    linewidth=1.5,
                    color=colors[b],
                    alpha=0.7,
                )

        self.ax.set_xticks(x)
        self.ax.set_xticklabels(
            [d.strftime("%b %d") for d in dates],
            rotation=30,
            ha="right",
            fontsize=8,
        )

        self.ax.set_ylabel("Balance ($)")
        self.ax.legend()
        self.fig.tight_layout()

        self.canvas.draw()

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        """Refresh the savings transaction table."""
        for r in self.tree.get_children():
            self.tree.delete(r)

        rows = self.savings_service.savings_transactions_table()

        for row in rows:
            date_s, bucket, direction, amount, category, desc = row
            sign = "+" if direction == "To Savings" else "-"
            self.tree.insert(
                "",
                "end",
                values=(
                    date_s,
                    bucket,
                    direction,
                    f"{sign}${amount:,.2f}",
                    category,
                    desc,
                ),
            )
