"""
Dashboard page for the Budget Planner.

Displays:
- Monthly income
- Monthly expenses
- Weekly spending
- Total debt
- Running total
- Total savings
- Budget alerts
- Recent transactions

This page mirrors the original UI but is fully modular and SQLite‑powered.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import TYPE_CHECKING

from ui.widgets import Card, ScrollablePage, StatCard, FONT, TEXT, TEXT_SEC, CARD_BG, BG, WARNING, SUCCESS, DANGER
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

if TYPE_CHECKING:
    from ui.app import App


class DashboardPage(ScrollablePage):
    """
    Dashboard page showing financial summaries and recent activity.
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: "App",
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

        # StringVars for stat cards
        self.var_income = tk.StringVar(value="$0.00")
        self.var_expenses = tk.StringVar(value="$0.00")
        self.var_week = tk.StringVar(value="$0.00")
        self.var_debt = tk.StringVar(value="$0.00")
        self.var_running = tk.StringVar(value="$0.00")
        self.var_savings = tk.StringVar(value="$0.00")

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the dashboard layout with scroll support."""

        container = tk.Frame(self.inner, bg=BG)
        container.pack(fill="both", expand=True, padx=28, pady=20)

        # --- Row 1: Income / Expenses / Week ---
        row1 = tk.Frame(container, bg=BG)
        row1.pack(fill="x", pady=(0, 16))
        self.summary_row_1 = row1

        for i in range(3):
            row1.columnconfigure(i, weight=1, uniform="stat")

        self.card_income = StatCard(row1, "Monthly Income", self.var_income, SUCCESS)
        self.card_income.grid(row=0, column=0, padx=5, sticky="nsew")

        self.card_expenses = StatCard(row1, "Monthly Expenses", self.var_expenses, DANGER)
        self.card_expenses.grid(row=0, column=1, padx=5, sticky="nsew")

        self.card_week = StatCard(row1, "This Week Spent", self.var_week, WARNING)
        self.card_week.grid(row=0, column=2, padx=5, sticky="nsew")

        # --- Row 2: Debt / Running Total / Savings ---
        row2 = tk.Frame(container, bg=BG)
        row2.pack(fill="x", pady=(0, 16))
        self.summary_row_2 = row2

        for i in range(3):
            row2.columnconfigure(i, weight=1, uniform="stat2")

        StatCard(row2, "Total Debt", self.var_debt, DANGER).grid(
            row=0, column=0, padx=5, sticky="nsew"
        )
        StatCard(row2, "Running Total", self.var_running, "#2563eb").grid(
            row=0, column=1, padx=5, sticky="nsew"
        )
        StatCard(row2, "Total Savings", self.var_savings, SUCCESS).grid(
            row=0, column=2, padx=5, sticky="nsew"
        )

        # --- Alerts ---
        self.alert_card = Card(container)
        self.alert_card.pack(fill="x", pady=(0, 16))
        self.alert_inner = tk.Frame(self.alert_card, bg=CARD_BG)
        self.alert_inner.pack(fill="x")

        # --- Recent Transactions ---
        recent_card = Card(container, pady=12, padx=0)
        recent_card.pack(fill="both", expand=True)

        tk.Label(
            recent_card,
            text="  Recent Transactions",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
            anchor="w",
        ).pack(fill="x", padx=16, pady=(6, 8))

        cols = ("date", "type", "category", "vendor", "description", "amount")
        self.tree = ttk.Treeview(recent_card, columns=cols, show="headings", height=10)
        for c, w, a in [
            ("date", 100, "w"),
            ("type", 100, "center"),
            ("category", 130, "w"),
            ("vendor", 150, "w"),
            ("description", 220, "w"),
            ("amount", 110, "e"),
        ]:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor=a)

        recent_scroll = tk.Scrollbar(recent_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=recent_scroll.set)
        recent_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=(0, 6))

    # ------------------------------------------------------------------
    # Refresh Logic
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh dashboard data from SQLite."""

        now = datetime.today()
        summary = self.tx_repo.month_summary(now.month, now.year)

        # Stat cards
        self.var_income.set(f"${summary['income']:,.2f}")
        self.var_expenses.set(f"${summary['expenses']:,.2f}")
        self.var_week.set(f"${self.tx_repo.week_expenses():,.2f}")
        self.var_debt.set(f"${self.debt_repo.total_debt():,.2f}")
        self.var_running.set(f"${self.tx_repo.running_total():,.2f}")
        self.var_savings.set(f"${self.savings_service.total_savings():,.2f}")

        # Alerts
        for w in self.alert_inner.winfo_children():
            w.destroy()

        alerts = self.budget_repo.alerts(self.tx_repo, now.month, now.year)
        if alerts:
            tk.Label(
                self.alert_inner,
                text="Budget",
                font=(FONT, 12, "bold"),
                fg=TEXT,
                bg=CARD_BG,
            ).pack(anchor="w", pady=(0, 6))

            for cat, spent, limit_amt, pct, level in alerts:
                color = DANGER if level == "over" else WARNING if level == "warn" else SUCCESS
                icon = "🚨" if level == "over" else "⚠️" if level == "warn" else "✅"

                tk.Label(
                    self.alert_inner,
                    text=f"{icon}  {cat}: ${spent:,.2f} / ${limit_amt:,.2f} ({pct:.0f}%)",
                    font=(FONT, 10, "bold"),
                    fg=color,
                    bg=CARD_BG,
                ).pack(anchor="w")

            self.alert_card.pack(fill="x", pady=(0, 16))
        else:
            self.alert_card.pack_forget()

        # Recent transactions
        for r in self.tree.get_children():
            self.tree.delete(r)

        for t in self.tx_repo.all()[:12]:
            # Display type
            if t.type == "savings_spend":
                display_type = "Savings Spend"
            else:
                display_type = t.type.title()

            # Amount sign logic
            if t.type == "income":
                sign = "+"
            elif t.type == "expense":
                sign = "-"
            elif t.type == "savings_spend":
                # Spending from savings is an outflow from savings,
                # but not new income; show as negative.
                sign = "-"
            elif t.type == "debt_payment":
                # Debt payments reduce debt but are an outflow of cash; show as negative.
                sign = "-"
            else:
                sign = ""

            amount_str = f"{sign}${t.amount:,.2f}"

            self.tree.insert(
                "",
                "end",
                values=(
                    t.date,
                    display_type,
                    t.category,
                    t.vendor,
                    t.description,
                    amount_str,
                ),
            )
