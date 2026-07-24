"""
Budget Limits page for the Budget Planner.

Integrated with the Budget Advisor system.

Now includes:
- Global monthly income header (last month + expected override)
- Slider-based manual budgeting (0.25% increments, dollar-only display)
- Static and dynamic slider behavior
- Advisor integration that can feed into sliders
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List

from ui.widgets import (
    Card, ScrollablePage, FONT, TEXT, TEXT_SEC, CARD_BG, BG,
    PRIMARY, PRIMARY_HOVER,
)
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService
from data.budget_advisor import BudgetAdvisorService, EventGoal, HistoryMode

if TYPE_CHECKING:
    from ui.app import App


CATEGORY_DEBT_LABEL_TO_CODE = {
    "None": None,
    "Utility Bill": "utility",
    "Credit Card": "credit",
    "Loan": "loan",
    "Other Debt": "other",
}

CATEGORY_DEBT_CODE_TO_LABEL = {
    value: key for key, value in CATEGORY_DEBT_LABEL_TO_CODE.items()
}


class BudgetsPage(ScrollablePage):
    """
    Page for managing budget limits and using the Budget Advisor.

    Features:
    - Global monthly income header (last month + expected override)
    - Generate recommended budgets via the Advisor
    - View recommended budgets and insights
    - Slider-based manual budgeting (0.25% increments, dollar-only)
    - Apply manual budgets to categories
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: App,
        tx_repo: TransactionRepository,
        debt_repo: DebtRepository,
        budget_repo: BudgetRepository,
        savings_service: SavingsService,
        history_mode_var: HistoryMode = "6m",
    ) -> None:
        super().__init__(parent, bg=BG)

        self.app = app
        self.tx_repo = tx_repo
        self.debt_repo = debt_repo
        self.budget_repo = budget_repo
        self.savings_service = savings_service

        self.mode_var = tk.StringVar(value="balanced")
        self.history_mode_var = tk.StringVar(value=history_mode_var)
        self.event_name_var = tk.StringVar()
        self.event_amount_var = tk.StringVar()
        self.event_date_var = tk.StringVar()
        self.category_kind_var = tk.StringVar(value="expense")
        self.selected_category_var = tk.StringVar()
        self.category_name_var = tk.StringVar()
        self.template_category_var = tk.StringVar()
        self.suggestion_category_var = tk.StringVar()
        self.category_group_var = tk.StringVar(value="wants")
        self.category_debt_type_var = tk.StringVar(value="None")
        self.category_is_savings_var = tk.BooleanVar(value=False)

        # Income header state
        self.last_month_income: float = self._compute_last_month_income()
        self.income_override_var = tk.StringVar()

        # Slider state
        self.dynamic_mode_var = tk.BooleanVar(value=False)
        self.slider_vars: Dict[str, tk.IntVar] = {}
        self.slider_amount_labels: Dict[str, tk.Label] = {}
        self.slider_scales: Dict[str, ttk.Scale] = {}
        self._updating_sliders = False  # guard to avoid recursion
        self._active_slider = None
        self._active_slider_max_ticks = 0
        self.slider_rows_frame: tk.Frame | None = None


        self.advisor = BudgetAdvisorService(
            tx_repo=self.tx_repo,
            debt_repo=self.debt_repo,
            savings_service=self.savings_service,
            budget_repo=self.budget_repo,
            category_repo=self.app.category_repo,
            mode="balanced",
        )

        # Pre-fill override with last month's income
        if self.last_month_income > 0:
            self.income_override_var.set(f"{self.last_month_income:.2f}")
        else:
            self.income_override_var.set("")

        self._build_ui()

    # ------------------------------------------------------------------
    # Helpers: Income
    # ------------------------------------------------------------------

    def _compute_last_month_income(self) -> float:
        """Compute last month's income from transaction history."""
        today = datetime.today().date()
        last_month_date = (today.replace(day=1) - timedelta(days=1))
        last_month = last_month_date.month
        last_year = last_month_date.year

        total = 0.0
        for t in self.tx_repo.history():
            try:
                t_date = datetime.strptime(t.date, "%Y-%m-%d").date()
            except Exception:
                continue
            if getattr(t, "type", "") == "income" and t_date.month == last_month and t_date.year == last_year:
                total += t.amount
        return total

    def _get_effective_income(self) -> float:
        """
        Hybrid income logic:
        - If override is a valid positive number, use it.
        - Otherwise, fall back to last month's income.
        """
        override_str = self.income_override_var.get().strip()
        if override_str:
            try:
                val = float(override_str)
                if val > 0:
                    return val
            except ValueError:
                pass
        return self.last_month_income

    def _refresh_income_display(self) -> None:
        """Update the last month's income label and refresh sliders."""
        self.last_month_income = self._compute_last_month_income()
        self.last_income_label.config(text=f"${self.last_month_income:,.2f}")
        self.income_override_var.set(f"{self.last_month_income:.2f}")
        self.effective_income = self._get_effective_income()
        self._load_sliders_from_saved_budgets()
        self._update_all_amount_labels()

    def _expense_category_names(self) -> List[str]:
        return self.app.category_repo.names("expense")

    def _load_sliders_from_saved_budgets(self) -> None:
        income = self._get_effective_income()
        budget_limits = {budget.category: budget.limit_amount for budget in self.budget_repo.all()}

        self._updating_sliders = True
        try:
            for cat, var in self.slider_vars.items():
                amount = budget_limits.get(cat, 0.0)
                if income <= 0 or amount <= 0:
                    var.set(0)
                    continue

                percent = (amount / income) * 100.0
                ticks = max(0, min(400, int(round(percent / 0.25))))
                var.set(ticks)
        finally:
            self._updating_sliders = False

    def _rebuild_slider_rows(self) -> None:
        if self.slider_rows_frame is None:
            return

        existing_ticks = {cat: var.get() for cat, var in self.slider_vars.items()}

        for child in self.slider_rows_frame.winfo_children():
            child.destroy()

        self.slider_vars = {}
        self.slider_amount_labels = {}
        self.slider_scales = {}

        for cat in self._expense_category_names():
            row = tk.Frame(self.slider_rows_frame, bg=CARD_BG)
            row.pack(fill="x", pady=3)

            tk.Label(
                row,
                text=cat,
                font=(FONT, 10),
                fg=TEXT,
                bg=CARD_BG,
                width=18,
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, 6))

            var = tk.IntVar(value=existing_ticks.get(cat, 0))
            self.slider_vars[cat] = var

            row.grid_columnconfigure(1, weight=1)

            slider = ttk.Scale(
                row,
                from_=0,
                to=400,
                orient="horizontal",
                variable=var,
                command=lambda v, c=cat: self._on_slider_change(c, float(v)),
            )
            slider.bind("<ButtonPress-1>", lambda e, c=cat: self._on_slider_press(c))
            slider.bind("<ButtonRelease-1>", lambda e, c=cat: self._on_slider_release(c))
            slider.grid(row=0, column=1, sticky="ew", padx=(4, 4))
            self.slider_scales[cat] = slider

            amt_label = tk.Label(
                row,
                text="$0",
                font=(FONT, 10),
                fg=TEXT_SEC,
                bg=CARD_BG,
                width=10,
                anchor="e",
            )
            amt_label.grid(row=0, column=2, sticky="e", padx=(6, 0))
            self.slider_amount_labels[cat] = amt_label

        self._load_sliders_from_saved_budgets()
        self._update_all_amount_labels()

    def _refresh_category_manager(self) -> None:
        kind = self.category_kind_var.get() or "expense"
        values = self.app.category_repo.names(kind)
        self.category_select_combo.configure(values=values)

        current = self.selected_category_var.get().strip()
        if current and current in values:
            self.category_select_combo.set(current)
        elif values:
            self.selected_category_var.set(values[0])
            self.category_select_combo.set(values[0])
        else:
            self.selected_category_var.set("")
            self.category_select_combo.set("")

        self._refresh_template_options(kind)
        self._refresh_suggestion_options(kind)
        self._load_selected_category_details()

    def _refresh_template_options(self, kind: str) -> None:
        values = self.app.category_repo.available_template_names(kind)
        self.template_select_combo.configure(values=values)

        current = self.template_category_var.get().strip()
        if current and current in values:
            self.template_select_combo.set(current)
        elif values:
            self.template_category_var.set(values[0])
            self.template_select_combo.set(values[0])
        else:
            self.template_category_var.set("")
            self.template_select_combo.set("")

    def _refresh_suggestion_options(self, kind: str) -> None:
        suggestions = self.app.category_repo.list_suggestions(kind)
        values = [suggestion.name for suggestion in suggestions]
        self.suggestion_select_combo.configure(values=values)

        current = self.suggestion_category_var.get().strip()
        if current and current in values:
            self.suggestion_select_combo.set(current)
        elif values:
            self.suggestion_category_var.set(values[0])
            self.suggestion_select_combo.set(values[0])
        else:
            self.suggestion_category_var.set("")
            self.suggestion_select_combo.set("")

    def _on_category_kind_change(self) -> None:
        self._refresh_category_manager()

    def _on_category_selected(self) -> None:
        self._load_selected_category_details()

    def _load_selected_category_details(self) -> None:
        selected_name = self.selected_category_var.get().strip()
        kind = self.category_kind_var.get().strip() or "expense"
        category = self.app.category_repo.get(selected_name, kind, include_inactive=False)

        if category is None:
            self.category_name_var.set("")
            self.category_group_var.set("wants")
            self.category_debt_type_var.set("None")
            self.category_is_savings_var.set(False)
            self._sync_category_detail_controls()
            return

        self.category_name_var.set(category.name)
        self.category_group_var.set(category.advisor_group)
        self.category_debt_type_var.set(CATEGORY_DEBT_CODE_TO_LABEL.get(category.debt_type, "None"))
        self.category_is_savings_var.set(category.is_savings)
        self._sync_category_detail_controls()

    def _sync_category_detail_controls(self) -> None:
        is_income = self.category_kind_var.get().strip() == "income"
        is_savings = bool(self.category_is_savings_var.get())

        if is_income:
            self.category_group_var.set("wants")
            self.category_debt_type_var.set("None")
            self.category_is_savings_var.set(False)
            self.category_group_combo.configure(state="disabled")
            self.category_debt_combo.configure(state="disabled")
            self.category_savings_check.configure(state="disabled")
            return

        self.category_group_combo.configure(state="readonly")
        self.category_savings_check.configure(state="normal")

        if is_savings:
            self.category_group_var.set("financial")
            self.category_debt_type_var.set("None")
            self.category_debt_combo.configure(state="disabled")
        else:
            self.category_debt_combo.configure(state="readonly")

    def _category_metadata_kwargs(self) -> dict:
        kind = self.category_kind_var.get().strip() or "expense"
        if kind == "income":
            return {}

        is_savings = bool(self.category_is_savings_var.get())
        debt_type = CATEGORY_DEBT_LABEL_TO_CODE.get(self.category_debt_type_var.get().strip(), None)
        advisor_group = self.category_group_var.get().strip() or "wants"
        return {
            "advisor_group": advisor_group,
            "debt_type": debt_type,
            "is_savings": is_savings,
        }

    def _add_category(self) -> None:
        name = self.category_name_var.get().strip()
        kind = self.category_kind_var.get().strip() or "expense"
        if not name:
            messagebox.showerror("Missing Name", "Enter a category name to add.")
            return

        self.app.category_repo.ensure_category(name, kind, **self._category_metadata_kwargs())
        self.category_name_var.set("")
        self.selected_category_var.set(name)

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Category Added", f"Added '{name}' to {kind} categories.")

    def _rename_category(self) -> None:
        current_name = self.selected_category_var.get().strip()
        new_name = self.category_name_var.get().strip()
        kind = self.category_kind_var.get().strip() or "expense"

        if not current_name:
            messagebox.showerror("No Category", "Select a category to rename.")
            return
        if not new_name:
            messagebox.showerror("Missing Name", "Enter the new category name.")
            return

        try:
            self.app.category_repo.update_category(
                current_name,
                kind,
                new_name=new_name,
                **self._category_metadata_kwargs(),
            )
        except ValueError as exc:
            messagebox.showerror("Rename Failed", str(exc))
            return

        self.category_name_var.set("")
        self.selected_category_var.set(new_name)

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Category Saved", f"Saved category settings for '{new_name}'.")

    def _delete_category(self) -> None:
        current_name = self.selected_category_var.get().strip()
        kind = self.category_kind_var.get().strip() or "expense"

        if not current_name:
            messagebox.showerror("No Category", "Select a category to delete.")
            return

        if not messagebox.askyesno(
            "Archive Category",
            "Archive this category from future use? Historical transactions will keep their original label.",
        ):
            return

        try:
            self.app.category_repo.delete_category(current_name, kind)
        except ValueError as exc:
            messagebox.showerror("Delete Failed", str(exc))
            return

        self.category_name_var.set("")

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Category Archived", f"Archived '{current_name}' from active categories.")

    def _import_template_category(self) -> None:
        kind = self.category_kind_var.get().strip() or "expense"
        name = self.template_category_var.get().strip()
        if not name:
            messagebox.showerror("No Template", "Select a template category to import.")
            return

        self.app.category_repo.import_templates([name], kind)
        self.selected_category_var.set(name)

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Template Imported", f"Imported '{name}' to active {kind} categories.")

    def _import_suggestion_category(self) -> None:
        kind = self.category_kind_var.get().strip() or "expense"
        name = self.suggestion_category_var.get().strip()
        if not name:
            messagebox.showerror("No Suggestion", "Select a suggested category to import.")
            return

        self.app.category_repo.import_suggestion(
            name,
            kind,
            **self._category_metadata_kwargs(),
        )
        self.selected_category_var.set(name)

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Suggestion Imported", f"Imported '{name}' to active {kind} categories.")

    def _ignore_suggestion_category(self) -> None:
        kind = self.category_kind_var.get().strip() or "expense"
        name = self.suggestion_category_var.get().strip()
        if not name:
            messagebox.showerror("No Suggestion", "Select a suggested category to ignore.")
            return

        self.app.category_repo.ignore_suggestion(name, kind)

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()

        messagebox.showinfo("Suggestion Hidden", f"Ignored '{name}' suggestion for {kind} categories.")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ------------------------------------------------------------------
        # Income Header
        # ------------------------------------------------------------------
        income_card = Card(self.inner, padx=16, pady=12)
        income_card.pack(fill="x", padx=28, pady=(16, 8))

        tk.Label(
            income_card,
            text="Monthly Income",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 6))

        income_row = tk.Frame(income_card, bg=CARD_BG)
        income_row.pack(fill="x", pady=(0, 4))

        income_row.grid_columnconfigure(0, weight=0)
        income_row.grid_columnconfigure(1, minsize=12)
        income_row.grid_columnconfigure(2, minsize=120)

        tk.Label(
            income_row,
            text="Last Month's Income:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        self.last_income_label = tk.Label(
            income_row,
            text=f"${self.last_month_income:,.2f}",
            font=(FONT, 10),
            fg=TEXT,
            bg=CARD_BG,
        )
        self.last_income_label.grid(row=0, column=2, sticky="w")

        tk.Label(
            income_row,
            text="Expected Monthly Income:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        tk.Label(
            income_row,
            text="$",
            font=(FONT, 10, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).grid(row=1, column=1, sticky="e", pady=(6, 0))

        income_entry = tk.Entry(
            income_row,
            textvariable=self.income_override_var,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            width=14,
        )
        income_entry.grid(row=1, column=2, sticky="w", pady=(6, 0))

        income_entry.bind("<KeyRelease>", lambda e: self._update_all_amount_labels())
        income_entry.bind("<FocusOut>", lambda e: self._update_all_amount_labels())
        
        refresh_btn = tk.Button(income_row, 
                                text="Refresh", 
                                font=(FONT, 10, "bold"), 
                                bg=PRIMARY, 
                                fg="#ffffff", 
                                activebackground=PRIMARY_HOVER, 
                                command=self._refresh_income_display)
        refresh_btn.grid(row=1, column=3, sticky="e", padx=(0, 28), pady=(0, 8))

        # ------------------------------------------------------------------
        # Advisor Card
        # ------------------------------------------------------------------
        advisor_card = Card(self.inner, padx=16, pady=12)
        advisor_card.pack(fill="x", padx=28, pady=(8, 8))

        header_frame = tk.Frame(advisor_card, bg=CARD_BG)
        header_frame.pack(fill="x")

        self.advisor_open = tk.BooleanVar(value=True)

        def toggle_advisor():
            if self.advisor_open.get():
                advisor_body.pack_forget()
                self.advisor_open.set(False)
                toggle_btn.configure(text="▶ Budget Advisor")
            else:
                advisor_body.pack(fill="both", expand=True, pady=(8, 0))
                self.advisor_open.set(True)
                toggle_btn.configure(text="▼ Budget Advisor")

        toggle_btn = tk.Button(
            header_frame,
            text="▼ Budget Advisor",
            font=(FONT, 12, "bold"),
            bg=CARD_BG,
            fg=TEXT,
            activebackground=CARD_BG,
            activeforeground=TEXT,
            relief="flat",
            cursor="hand2",
            command=toggle_advisor,
        )
        toggle_btn.pack(side="left", anchor="w")

        advisor_body = tk.Frame(advisor_card, bg=CARD_BG)
        advisor_body.pack(fill="both", expand=True, pady=(8, 0))

        adv_inner = tk.Frame(advisor_body, bg=CARD_BG)
        adv_inner.pack(fill="both", expand=True)

        # Mode selection
        mode_frame = tk.Frame(adv_inner, bg=CARD_BG)
        mode_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            mode_frame,
            text="Budgeting Mode:",
            font=(FONT, 10, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        modes = [
            ("Balanced", "balanced"),
            ("Prioritize Savings", "savings"),
            ("Prioritize Debt", "debt"),
            ("Plan Event", "event"),
        ]
        for i, (label, value) in enumerate(modes, start=1):
            tk.Radiobutton(
                mode_frame,
                text=label,
                variable=self.mode_var,
                value=value,
                font=(FONT, 10),
                fg=TEXT,
                bg=CARD_BG,
                activebackground=CARD_BG,
                anchor="w",
                command=self._on_mode_change,
            ).grid(row=i, column=0, sticky="w")

        # History mode selection
        history_frame = tk.Frame(adv_inner, bg=CARD_BG)
        history_frame.pack(fill="x", pady=(4, 8))

        tk.Label(
            history_frame,
            text="History Window:",
            font=(FONT, 10, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        history_options = [
            ("Last 3 months", "3m"),
            ("Last 6 months", "6m"),
            ("Last 12 months", "12m"),
            ("Seasonal (last 12m, seasonal weights)", "seasonal"),
            ("All history", "all"),
        ]

        history_combo = ttk.Combobox(
            history_frame,
            textvariable=self.history_mode_var,
            values=[label for label, _ in history_options],
            state="readonly",
            width=32,
        )
        history_combo.grid(row=0, column=1, sticky="w")

        # Map label → code and keep a reverse lookup
        self._history_label_to_code = {label: code for label, code in history_options}
        self._history_code_to_label = {code: label for label, code in history_options}

        # Initialize combo to current history_mode
        history_combo.set(self._history_code_to_label.get("6m", "Last 6 months"))

        def _on_history_change(event=None):
            label = history_combo.get()
            code = self._history_label_to_code.get(label, "6m")
            self.history_mode_var.set(code)

        history_combo.bind("<<ComboboxSelected>>", _on_history_change)

        # Event config
        self.event_frame = tk.Frame(adv_inner, bg=CARD_BG)
        self.event_frame.pack(fill="x", pady=(4, 8))

        tk.Label(
            self.event_frame,
            text="Event Name:",
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        tk.Entry(
            self.event_frame,
            textvariable=self.event_name_var,
            font=(FONT, 9),
            width=18,
        ).grid(row=0, column=1, sticky="w")

        tk.Label(
            self.event_frame,
            text="Target Amount:",
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=2, sticky="w", padx=(12, 6))
        tk.Entry(
            self.event_frame,
            textvariable=self.event_amount_var,
            font=(FONT, 9),
            width=10,
        ).grid(row=0, column=3, sticky="w")

        tk.Label(
            self.event_frame,
            text="Target Date (YYYY-MM):",
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=4, sticky="w", padx=(12, 6))
        tk.Entry(
            self.event_frame,
            textvariable=self.event_date_var,
            font=(FONT, 9),
            width=10,
        ).grid(row=0, column=5, sticky="w")

        # Advisor buttons
        adv_btn_frame = tk.Frame(adv_inner, bg=CARD_BG)
        adv_btn_frame.pack(fill="x", pady=(4, 8))

        tk.Button(
            adv_btn_frame,
            text="Generate Budget",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._generate_budget,
        ).pack(side="left")

        tk.Button(
            adv_btn_frame,
            text="Apply Recommended Budget",
            font=(FONT, 10, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._apply_budget,
        ).pack(side="left", padx=(8, 0))

        # Insights
        insights_card = Card(adv_inner, padx=10, pady=8)
        insights_card.pack(fill="x", pady=(4, 8))

        tk.Label(
            insights_card,
            text="Insights",
            font=(FONT, 11, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 4))

        self.insights_text = tk.Text(
            insights_card,
            height=6,
            font=(FONT, 9),
            bg=CARD_BG,
            fg=TEXT_SEC,
            relief="flat",
            wrap="word",
        )
        self.insights_text.pack(fill="both", expand=True)
        self.insights_text.configure(state="disabled")

        # Recommended budget table
        rec_card = Card(adv_inner, padx=10, pady=8)
        rec_card.pack(fill="both", expand=True, pady=(4, 0))

        tk.Label(
            rec_card,
            text="Recommended Budget",
            font=(FONT, 11, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 4))

        rec_cols = ("category", "amount")
        self.rec_tree = ttk.Treeview(rec_card, columns=rec_cols, show="headings", height=8)
        self.rec_tree.heading("category", text="Category")
        self.rec_tree.heading("amount", text="Amount")
        self.rec_tree.column("category", width=260, anchor="w")
        self.rec_tree.column("amount", width=120, anchor="e")

        rec_scroll = tk.Scrollbar(rec_card, orient="vertical", command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rec_scroll.set)
        rec_scroll.pack(side="right", fill="y")
        self.rec_tree.pack(side="left", fill="both", expand=True)

        # ------------------------------------------------------------------
        # Manual Budgets Card (Slider-based)
        # ------------------------------------------------------------------
        manual_card = Card(self.inner, padx=16, pady=12)
        manual_card.pack(fill="both", expand=True, padx=28, pady=(8, 20))

        tk.Label(
            manual_card,
            text="Manual Budget Limits",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 6))

        # Dynamic mode checkbox
        dyn_frame = tk.Frame(manual_card, bg=CARD_BG)
        dyn_frame.pack(fill="x", pady=(0, 8))

        tk.Checkbutton(
            dyn_frame,
            text="Dynamic Mode (auto-adjust other sliders)",
            variable=self.dynamic_mode_var,
            font=(FONT, 10),
            fg=TEXT_SEC,
            bg=CARD_BG,
            activebackground=CARD_BG,
            anchor="w",
        ).pack(anchor="w")

        # Sliders container
        self.slider_rows_frame = tk.Frame(manual_card, bg=CARD_BG)
        self.slider_rows_frame.pack(fill="x", pady=(4, 8))
        self._rebuild_slider_rows()

        btn_frame = tk.Frame(manual_card, bg=CARD_BG)
        btn_frame.pack(fill="x", pady=(8, 0))

        tk.Button(
            btn_frame,
            text="Apply Manual Budget",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._apply_manual_budget,
        ).pack(side="left")

        manager = Card(self.inner, padx=16, pady=12)
        manager.pack(fill="x", padx=28, pady=(0, 20))

        tk.Label(
            manager,
            text="Manage Categories",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 6))

        tk.Label(
            manager,
            text="Add, edit, or delete categories. Historical transactions keep their original category labels even after category settings change.",
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        grid = tk.Frame(manager, bg=CARD_BG)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)

        tk.Label(grid, text="Type", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=0, column=0, sticky="w")
        kind_combo = ttk.Combobox(
            grid,
            textvariable=self.category_kind_var,
            values=["expense", "income"],
            state="readonly",
            width=18,
            font=(FONT, 10),
        )
        kind_combo.grid(row=1, column=0, sticky="w", pady=(2, 10), padx=(0, 16))
        kind_combo.bind("<<ComboboxSelected>>", lambda e: self._on_category_kind_change())

        tk.Label(grid, text="Existing Category", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=0, column=1, sticky="w")
        self.category_select_combo = ttk.Combobox(
            grid,
            textvariable=self.selected_category_var,
            values=[],
            state="readonly",
            width=32,
            font=(FONT, 10),
        )
        self.category_select_combo.grid(row=1, column=1, sticky="ew", pady=(2, 10), padx=(0, 16))
        self.category_select_combo.bind("<<ComboboxSelected>>", lambda e: self._on_category_selected())

        tk.Label(grid, text="Name", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=0, column=2, sticky="w")
        tk.Entry(
            grid,
            textvariable=self.category_name_var,
            width=28,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
        ).grid(row=1, column=2, sticky="ew", pady=(2, 10), padx=(0, 16), ipady=3)

        tk.Label(grid, text="Budget Group", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=2, column=0, sticky="w")
        self.category_group_combo = ttk.Combobox(
            grid,
            textvariable=self.category_group_var,
            values=["needs", "wants", "financial"],
            state="readonly",
            width=18,
            font=(FONT, 10),
        )
        self.category_group_combo.grid(row=3, column=0, sticky="w", pady=(2, 10), padx=(0, 16))

        tk.Label(grid, text="Debt Behavior", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=2, column=1, sticky="w")
        self.category_debt_combo = ttk.Combobox(
            grid,
            textvariable=self.category_debt_type_var,
            values=list(CATEGORY_DEBT_LABEL_TO_CODE.keys()),
            state="readonly",
            width=18,
            font=(FONT, 10),
        )
        self.category_debt_combo.grid(row=3, column=1, sticky="w", pady=(2, 10), padx=(0, 16))

        self.category_savings_check = tk.Checkbutton(
            grid,
            text="Treat as Savings category",
            variable=self.category_is_savings_var,
            font=(FONT, 10),
            fg=TEXT_SEC,
            bg=CARD_BG,
            activebackground=CARD_BG,
            command=self._sync_category_detail_controls,
        )
        self.category_savings_check.grid(row=3, column=2, sticky="w", pady=(2, 10))

        actions = tk.Frame(manager, bg=CARD_BG)
        actions.pack(fill="x")

        tk.Button(
            actions,
            text="Add Category",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._add_category,
        ).pack(side="left")

        tk.Button(
            actions,
            text="Save Changes",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._rename_category,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            actions,
            text="Archive Category",
            font=(FONT, 10, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._delete_category,
        ).pack(side="left", padx=(8, 0))

        extras = tk.Frame(manager, bg=CARD_BG)
        extras.pack(fill="x", pady=(12, 0))
        extras.grid_columnconfigure(1, weight=1)

        tk.Label(extras, text="Optional Templates", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=0, column=0, sticky="w")
        self.template_select_combo = ttk.Combobox(
            extras,
            textvariable=self.template_category_var,
            values=[],
            state="readonly",
            width=32,
            font=(FONT, 10),
        )
        self.template_select_combo.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        tk.Button(
            extras,
            text="Import Template",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._import_template_category,
        ).grid(row=0, column=2, sticky="e")

        tk.Label(extras, text="History Suggestions", font=(FONT, 10, "bold"), fg=TEXT_SEC, bg=CARD_BG).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.suggestion_select_combo = ttk.Combobox(
            extras,
            textvariable=self.suggestion_category_var,
            values=[],
            state="readonly",
            width=32,
            font=(FONT, 10),
        )
        self.suggestion_select_combo.grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(10, 0))

        suggestion_actions = tk.Frame(extras, bg=CARD_BG)
        suggestion_actions.grid(row=1, column=2, sticky="e", pady=(10, 0))
        tk.Button(
            suggestion_actions,
            text="Import Suggestion",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._import_suggestion_category,
        ).pack(side="left")
        tk.Button(
            suggestion_actions,
            text="Ignore",
            font=(FONT, 10, "bold"),
            bg="#475569",
            fg="#ffffff",
            activebackground="#334155",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._ignore_suggestion_category,
        ).pack(side="left", padx=(8, 0))

        self._refresh_category_manager()

        # Initialize advisor/event visibility and slider labels
        self._on_mode_change()
        self._load_sliders_from_saved_budgets()
        self._update_all_amount_labels()

    # ------------------------------------------------------------------
    # Advisor Logic
    # ------------------------------------------------------------------

    def _on_mode_change(self) -> None:
        mode = self.mode_var.get()
        if mode == "event":
            self.event_frame.pack(fill="x", pady=(4, 8))
        else:
            self.event_frame.pack_forget()

    def _build_event_goal(self) -> EventGoal | None:
        name = self.event_name_var.get().strip()
        amt_str = self.event_amount_var.get().strip()
        date_str = self.event_date_var.get().strip()

        if not name or not amt_str or not date_str:
            return None

        try:
            amount = float(amt_str)
        except ValueError:
            messagebox.showerror("Invalid Amount", "Event target amount must be a number.")
            return None

        try:
            dt = datetime.strptime(date_str + "-01", "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Invalid Date", "Event date must be in format YYYY-MM.")
            return None

        return EventGoal(name=name, target_amount=amount, target_date=dt)

    def _generate_budget(self) -> None:
        mode = self.mode_var.get()
        self.advisor.set_mode(mode)  # type: ignore[arg-type]

        # Apply history mode
        history_code = self.history_mode_var.get() or "6m"
        self.advisor.set_history_mode(history_code)  # type: ignore[arg-type]

        if mode == "event":
            goal = self._build_event_goal()
            if goal is None:
                return
            self.advisor.set_event_goal(goal)
        else:
            self.advisor.set_event_goal(None)

        rec = self.advisor.generate_recommendation()
        self._display_recommendation(rec)
        self._load_sliders_from_recommendation(rec)

    def _display_recommendation(self, rec) -> None:
        for row in self.rec_tree.get_children():
            self.rec_tree.delete(row)

        for cat, amt in sorted(rec.category_budgets.items()):
            self.rec_tree.insert("", "end", values=(cat, f"${amt:,.0f}"))

        self.insights_text.configure(state="normal")
        self.insights_text.delete("1.0", "end")
        for line in rec.insights:
            self.insights_text.insert("end", f"• {line}\n")
        self.insights_text.configure(state="disabled")

    def _apply_budget(self) -> None:
        mode = self.mode_var.get()
        self.advisor.set_mode(mode)  # type: ignore[arg-type]

        # Apply history mode
        history_code = self.history_mode_var.get() or "6m"
        self.advisor.set_history_mode(history_code)  # type: ignore[arg-type]

        if mode == "event":
            goal = self._build_event_goal()
            if goal is None:
                return
            self.advisor.set_event_goal(goal)
        else:
            self.advisor.set_event_goal(None)

        rec = self.advisor.generate_recommendation()
        self.advisor.apply_to_budgets(rec)
        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()
        messagebox.showinfo("Budget Applied", "Recommended budget has been applied to your categories.")

    def _load_sliders_from_recommendation(self, rec) -> None:
        """Set slider positions based on a BudgetRecommendation."""
        income = self._get_effective_income()
        if income <= 0:
            return

        self._updating_sliders = True
        try:
            for cat in self._expense_category_names():
                amt = rec.category_budgets.get(cat, 0.0)
                if cat not in self.slider_vars or amt <= 0:
                    if cat in self.slider_vars:
                        self.slider_vars[cat].set(0)
                    continue
                percent = (amt / income) * 100.0
                ticks = max(0, min(400, int(round(percent / 0.25))))
                self.slider_vars[cat].set(ticks)

            for cat in self.slider_vars:
                if cat in self._expense_category_names():
                    continue
                    self.slider_vars[cat].set(0)
        finally:
            self._updating_sliders = False

        self._update_all_amount_labels()

    # ------------------------------------------------------------------
    # Slider Logic
    # ------------------------------------------------------------------

    def _on_slider_change(self, category: str, raw_value: float) -> None:
        if self._updating_sliders:
            return

        self._updating_sliders = True
        try:
            new_ticks = int(round(raw_value))
            new_ticks = max(0, min(400, new_ticks))

            old_ticks = self.slider_vars[category].get()
            if new_ticks == old_ticks:
                self._updating_sliders = False
                self._update_all_amount_labels()
                return

            # STATIC MODE HARD CAP:
            # If we're in static mode and trying to increase this slider,
            # do not allow the total to exceed 100%.
            if not self.dynamic_mode_var.get() and new_ticks > old_ticks:
                # Current total percent with existing ticks
                total_percent = 0.0
                for cat, var in self.slider_vars.items():
                    total_percent += var.get() * 0.25

                current_percent_cat = old_ticks * 0.25
                others_percent = total_percent - current_percent_cat

                # Max percent this category is allowed to have
                max_for_cat = max(0.0, 100.0 - others_percent)
                max_ticks = int(round(max_for_cat / 0.25))
                max_ticks = max(0, min(400, max_ticks))

                if new_ticks > max_ticks:
                    new_ticks = max_ticks

            self.slider_vars[category].set(new_ticks)

            if self.dynamic_mode_var.get():
                self._redistribute_dynamic(category, old_ticks, new_ticks)
            else:
                # Static mode: we already clamped above; just ensure we don't drift
                self._clamp_static(category, new_ticks)
        finally:
            self._updating_sliders = False

        self._update_all_amount_labels()

    def _clamp_static(self, changed_cat: str, new_ticks: int) -> None:
        """
        Static mode safety: after the user moves a slider, ensure total never exceeds 100%.
        If it does, snap the changed slider back to the maximum allowed ticks.
        """
        # First, apply the user's requested value to the changed slider
        self.slider_vars[changed_cat].set(new_ticks)

        # Recompute total percent with this new value in place
        total_percent = 0.0
        for cat, var in self.slider_vars.items():
            total_percent += var.get() * 0.25

        # If we're within 100%, nothing to do
        if total_percent <= 100.0:
            return

        # How much percent is taken by all OTHER sliders?
        others_percent = 0.0
        for cat, var in self.slider_vars.items():
            if cat == changed_cat:
                continue
            others_percent += var.get() * 0.25

        # Whatever is left up to 100% is the max this slider is allowed to have
        allowed_for_this = max(0.0, 100.0 - others_percent)

        # Convert that back to ticks and clamp to [0, 400]
        allowed_ticks = int(round(allowed_for_this / 0.25))
        allowed_ticks = max(0, min(400, allowed_ticks))

        # Snap the changed slider back to its true max
        self.slider_vars[changed_cat].set(allowed_ticks)

    def _redistribute_dynamic(self, changed_cat: str, old_ticks: int, new_ticks: int) -> None:
        old_percent = old_ticks * 0.25
        new_percent = new_ticks * 0.25
        delta = new_percent - old_percent

        if delta <= 0:
            return

        others_percent = 0.0
        for cat, var in self.slider_vars.items():
            if cat == changed_cat:
                continue
            others_percent += var.get() * 0.25

        if others_percent <= 0:
            self._clamp_static(changed_cat, new_ticks)
            return

        total_if_unchanged = others_percent + new_percent
        if total_if_unchanged <= 100.0:
            return

        delta_needed = total_if_unchanged - 100.0
        remaining_others = max(0.0, others_percent - delta_needed)
        factor = remaining_others / others_percent if others_percent > 0 else 0.0

        for cat, var in self.slider_vars.items():
            if cat == changed_cat:
                continue
            current_percent = var.get() * 0.25
            new_other_percent = current_percent * factor
            new_other_ticks = int(round(new_other_percent / 0.25))
            new_other_ticks = max(0, min(400, new_other_ticks))
            var.set(new_other_ticks)

    def _update_all_amount_labels(self) -> None:
        income = self._get_effective_income()
        for cat, var in self.slider_vars.items():
            percent = var.get() * 0.25
            amount = income * (percent / 100.0) if income > 0 else 0.0
            amount_rounded = int(round(amount))
            label = self.slider_amount_labels.get(cat)
            if label is not None:
                label.config(text=f"${amount_rounded:,d}")

    def _on_slider_press(self, category: str):
        """Record which slider is active and compute its maximum allowed ticks."""
        self._active_slider = category

        income = self._get_effective_income()

        # Sum all other sliders in dollars
        others_dollars = 0
        for cat, var in self.slider_vars.items():
            if cat != category:
                percent = var.get() * 0.25
                others_dollars += income * (percent / 100.0)

        remaining = max(0, income - others_dollars)

        # Convert remaining dollars → ticks
        max_percent = (remaining / income) * 100.0 if income > 0 else 0
        max_ticks = int(max_percent / 0.25)

        self._active_slider_max_ticks = max(0, min(400, max_ticks))

    def _on_slider_release(self, category: str):
        """After slider movement ends, snap back to max allowed ticks."""
        if self.dynamic_mode_var.get():
            return
        
        else:
            if self._active_slider != category:
                return

            current_ticks = self.slider_vars[category].get()

            if current_ticks > self._active_slider_max_ticks:
                self.slider_vars[category].set(self._active_slider_max_ticks)

            self._active_slider = None
            self._update_all_amount_labels()

    # ------------------------------------------------------------------
    # Manual Budgets
    # ------------------------------------------------------------------

    def _apply_manual_budget(self) -> None:
        income = self._get_effective_income()
        if income <= 0:
            messagebox.showerror(
                "No Income",
                "Cannot apply manual budget because monthly income is zero or invalid.\n"
                "Please enter an Expected Monthly Income or ensure last month's income exists."
            )
            return

        for cat, var in self.slider_vars.items():
            percent = var.get() * 0.25
            if percent <= 0:
                continue
            amount = income * (percent / 100.0)
            amount_rounded = int(round(amount))
            if amount_rounded > 0:
                self.budget_repo.set_budget(cat, float(amount_rounded))

        if hasattr(self.app, "refresh_all"):
            self.app.refresh_all()
        messagebox.showinfo("Manual Budget Applied", "Manual slider-based budget has been applied to your categories.")

    def refresh(self) -> None:
        self._refresh_category_manager()
        self._rebuild_slider_rows()
        