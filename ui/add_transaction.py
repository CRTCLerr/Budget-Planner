"""
Add Transaction page.

Allows the user to:
- Add income or expense
- Move money to savings
- Spend from savings
- Apply an expense toward a debt (type-aware: utility, credit, loan)
- Select date via DateEntry

Visually mirrors the original monolithic app, but wired to SQLite and
the new data layer.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING, Dict, Any

from ui.widgets import (
    Card,
    DateEntry,
    ScrollablePage,
    FONT,
    TEXT_SEC,
    CARD_BG,
    PRIMARY,
    PRIMARY_HOVER,
    DANGER,
    SUCCESS,
)

from data.transactions import TransactionRepository
    # TransactionRepository now supports 'debt_payment' and legacy mapping
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

if TYPE_CHECKING:
    from ui.app import App

SAVINGS_BUCKETS = ["Savings", "E-Savings"]


class AddTransactionPage(ScrollablePage):
    """
    Page for adding new transactions.

    This is a tk.Frame subclass so it can be managed directly by the App.
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
        super().__init__(parent, bg="#f1f5f9")

        self.app = app
        self.tx_repo = tx_repo
        self.debt_repo = debt_repo
        self.budget_repo = budget_repo
        self.savings_service = savings_service

        # When coming from "Apply Payment" on the Debt page
        self.pending_debt_id: Optional[int] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = tk.Frame(self.inner, bg="#f1f5f9")
        pad.pack(fill="both", expand=True, padx=28, pady=20)

        card = Card(pad, padx=32, pady=28)
        card.pack(fill="x")

        tk.Label(
            card,
            text="New Transaction",
            font=(FONT, 14, "bold"),
            fg="#0f172a",
            bg=CARD_BG,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))

        r = 1

        # --- Type ---
        tk.Label(
            card,
            text="Type",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=r, column=0, sticky="w")
        r += 1

        self.var_type = tk.StringVar(value="expense")
        type_frame = tk.Frame(card, bg=CARD_BG)
        type_frame.grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14))

        tk.Radiobutton(
            type_frame,
            text="  Expense  ",
            variable=self.var_type,
            value="expense",
            font=(FONT, 10),
            bg=CARD_BG,
            fg=DANGER,
            selectcolor=CARD_BG,
            command=self._update_categories,
        ).pack(side="left", padx=(0, 12))

        tk.Radiobutton(
            type_frame,
            text="  Income  ",
            variable=self.var_type,
            value="income",
            font=(FONT, 10),
            bg=CARD_BG,
            fg=SUCCESS,
            selectcolor=CARD_BG,
            command=self._update_categories,
        ).pack(side="left")

        r += 1

        # --- Category ---
        tk.Label(
            card,
            text="Category",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=r, column=0, sticky="w")
        r += 1

        self.var_category = tk.StringVar()
        self.combo_category = ttk.Combobox(
            card,
            textvariable=self.var_category,
            values=self._category_names("expense"),
            state="normal",
            width=34,
            font=(FONT, 11),
        )
        self.combo_category.grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self.combo_category.bind("<<ComboboxSelected>>", lambda e: self._on_category_change())
        self.combo_category.bind("<KeyRelease>", lambda e: self._on_category_change())
        self.combo_category.bind("<FocusOut>", lambda e: self._on_category_change())

        r += 1

        # --- Amount ---
        tk.Label(
            card,
            text="Amount ($)",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=r, column=0, sticky="w")
        r += 1

        self.var_amount = tk.StringVar()
        tk.Entry(
            card,
            textvariable=self.var_amount,
            font=(FONT, 11),
            bg="#f8fafc",
            fg="#0f172a",
            relief="solid",
            bd=1,
            width=36,
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14), ipady=5)

        r += 1

        # --- Vendor / Source ---
        self.lbl_vendor = tk.Label(
            card,
            text="Vendor / Source",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        )
        self.lbl_vendor.grid(row=r, column=0, sticky="w")
        r += 1

        self.var_vendor = tk.StringVar()
        self.combo_vendor = ttk.Combobox(
            card,
            textvariable=self.var_vendor,
            values=[],
            state="normal",
            width=34,
            font=(FONT, 11),
        )
        self.combo_vendor.grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14))

        r += 1

        # --- Date ---
        tk.Label(
            card,
            text="Date",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=r, column=0, sticky="w")
        r += 1

        self.date_entry = DateEntry(card, bg_color=CARD_BG)
        self.date_entry.grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14))

        r += 1

        # --- Description ---
        tk.Label(
            card,
            text="Description",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=r, column=0, sticky="w")
        r += 1

        self.var_desc = tk.StringVar()
        tk.Entry(
            card,
            textvariable=self.var_desc,
            font=(FONT, 11),
            bg="#f8fafc",
            fg="#0f172a",
            relief="solid",
            bd=1,
            width=36,
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 14), ipady=5)

        r += 1

        # --- Savings UI ---
        self._build_savings_ui(card, r)
        r += 1

        # --- Debt UI ---
        self._build_debt_ui(card, r)
        r += 1

        # --- Submit Button ---
        tk.Button(
            card,
            text="Add Transaction",
            font=(FONT, 11, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._submit,
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))

        # Initialize category/savings/debt UI
        self._update_categories()
        self._refresh_debt_dropdown()

    def _category_names(self, kind: str) -> list[str]:
        return self.app.category_repo.names(kind)

    def _category_input(self) -> str:
        return self.var_category.get() or self.combo_category.get()

    def _selected_category(self) -> str:
        return self._category_input().strip()

    def _set_category_choices(self, kind: str, preferred: Optional[str] = None) -> None:
        values = self._category_names(kind)
        current = preferred.strip() if preferred else self._selected_category()
        self.combo_category.configure(values=values)

        if current and current in values:
            self.var_category.set(current)
            self.combo_category.set(current)
        elif values:
            self.var_category.set(values[0])
            self.combo_category.set(values[0])
        else:
            self.var_category.set("")
            self.combo_category.set("")

    def _selected_debt_type(self) -> Optional[str]:
        return self.app.category_repo.debt_type_for_category(self._selected_category())

    # ------------------------------------------------------------------
    # Category Logic
    # ------------------------------------------------------------------

    def _update_categories(self) -> None:
        """Switch category list based on income/expense."""
        if self.var_type.get() == "income":
            self._set_category_choices("income")
        else:
            self._set_category_choices("expense")
        self._update_savings_ui()
        self._update_debt_ui()
        self._refresh_debt_dropdown()
        self._refresh_vendor_dropdown()

    def _on_category_change(self) -> None:
        """Handle category change from the combobox."""
        self.var_category.set(self._category_input())
        self._update_savings_ui()
        self._update_debt_ui()
        self._refresh_debt_dropdown()

    def _refresh_vendor_dropdown(self) -> None:
        """Load source/vendor suggestions based on selected transaction mode."""
        tx_type = self.var_type.get()
        suggestions = self.tx_repo.vendor_suggestions(tx_type=tx_type)
        self.combo_vendor.configure(values=suggestions)

        if tx_type == "income":
            self.lbl_vendor.configure(text="Income Source")
        else:
            self.lbl_vendor.configure(text="Vendor")

    # ------------------------------------------------------------------
    # Savings UI
    # ------------------------------------------------------------------

    def _build_savings_ui(self, card: tk.Frame, row: int) -> None:
        """Create the savings-related UI elements."""
        self.savings_frame = tk.Frame(card, bg=CARD_BG)
        self.savings_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self.var_move = tk.BooleanVar(value=False)
        self.var_spend = tk.BooleanVar(value=False)
        self.var_bucket = tk.StringVar(value=SAVINGS_BUCKETS[0])

        self.chk_move = tk.Checkbutton(
            self.savings_frame,
            text="Move to Savings",
            variable=self.var_move,
            bg=CARD_BG,
            fg=SUCCESS,
            activebackground=CARD_BG,
            command=self._update_savings_ui,
        )

        self.chk_spend = tk.Checkbutton(
            self.savings_frame,
            text="Spend from Savings",
            variable=self.var_spend,
            bg=CARD_BG,
            fg=DANGER,
            activebackground=CARD_BG,
            command=self._update_savings_ui,
        )

        self.lbl_bucket = tk.Label(
            self.savings_frame,
            text="Savings Bucket:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        )

        self.combo_bucket = ttk.Combobox(
            self.savings_frame,
            textvariable=self.var_bucket,
            values=SAVINGS_BUCKETS,
            state="readonly",
            width=18,
            font=(FONT, 10),
        )
        self.combo_bucket.current(0)

        self._update_savings_ui()

    def _update_savings_ui(self) -> None:
        """Show/hide savings UI based on category and type."""
        for w in self.savings_frame.winfo_children():
            w.grid_forget()

        is_expense = self.var_type.get() == "expense"
        cat = self._selected_category()

        if not is_expense:
            self.var_move.set(False)
            self.var_spend.set(False)
            return

        if self.app.category_repo.is_savings_category(cat):
            # Only move to savings
            self.var_spend.set(False)
            self.chk_move.grid(row=0, column=0, sticky="w")
            if self.var_move.get():
                self.lbl_bucket.grid(row=0, column=1, padx=(8, 4))
                self.combo_bucket.grid(row=0, column=2)
        else:
            # Only spend from savings
            self.var_move.set(False)
            self.chk_spend.grid(row=0, column=0, sticky="w")
            if self.var_spend.get():
                self.lbl_bucket.grid(row=0, column=1, padx=(8, 4))
                self.combo_bucket.grid(row=0, column=2)

    # ------------------------------------------------------------------
    # Debt UI
    # ------------------------------------------------------------------

    def _build_debt_ui(self, card: tk.Frame, row: int) -> None:
        """Create the debt-related UI elements."""
        self.debt_frame = tk.Frame(card, bg=CARD_BG)
        self.debt_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self.var_apply_debt = tk.BooleanVar(value=False)
        self.var_debt_choice = tk.StringVar()

        self.chk_apply_debt = tk.Checkbutton(
            self.debt_frame,
            text="Apply this transaction toward a debt",
            variable=self.var_apply_debt,
            bg=CARD_BG,
            fg=PRIMARY,
            activebackground=CARD_BG,
            command=self._update_debt_ui,
        )

        self.lbl_debt = tk.Label(
            self.debt_frame,
            text="Select Debt:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        )

        self.combo_debt = ttk.Combobox(
            self.debt_frame,
            textvariable=self.var_debt_choice,
            values=[],
            state="readonly",
            width=34,
            font=(FONT, 10),
        )

        self._update_debt_ui()

    def _refresh_debt_dropdown(self) -> None:
        """Refresh the debt dropdown from the repository, filtered by category/debt type."""
        # Determine which debt type is allowed for the current category
        allowed_type = self._selected_debt_type()

        debts = self.debt_repo.all()
        items = []

        for d in debts:
            # DebtRepository.Debt now has .type
            d_type = getattr(d, "type", "other")
            if allowed_type is not None and d_type != allowed_type:
                continue
            did = d.id
            name = d.name
            remaining = d.remaining
            items.append(f"{did} - {name} (${remaining:,.2f})")

        self.combo_debt.configure(values=items)

        # If we have a pending debt id (from Debt page), preselect it if it matches allowed_type
        if self.pending_debt_id is not None:
            for i, text in enumerate(items):
                try:
                    did_str = text.split(" - ")[0]
                    if int(did_str) == self.pending_debt_id:
                        self.combo_debt.current(i)
                        self.var_debt_choice.set(text)
                        break
                except ValueError:
                    continue

    def _update_debt_ui(self) -> None:
        """Show/hide debt UI based on type, category, and checkbox."""
        for w in self.debt_frame.winfo_children():
            w.grid_forget()

        is_expense = self.var_type.get() == "expense"
        allowed_type = self._selected_debt_type()

        # Only allow debt application for categories that map to a debt type
        if not is_expense or allowed_type is None:
            self.var_apply_debt.set(False)
            return

        self.chk_apply_debt.grid(row=0, column=0, sticky="w")
        if self.var_apply_debt.get():
            self.lbl_debt.grid(row=0, column=1, padx=(8, 4), sticky="w")
            self.combo_debt.grid(row=0, column=2, sticky="w")

    def _parse_selected_debt_id(self) -> Optional[int]:
        """Parse the selected debt id from the combobox text."""
        text = self.var_debt_choice.get().strip()
        if not text:
            return None
        try:
            did_str = text.split(" - ")[0]
            return int(did_str)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Submit Logic
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        """Validate and add the transaction."""
        ttype = self.var_type.get()
        cat = self._selected_category()
        amt_s = self.var_amount.get().strip()
        desc = self.var_desc.get().strip()
        date_s = self.date_entry.get_date_str()

        if not cat:
            messagebox.showerror("Error", "Category is required.")
            return

        if not amt_s:
            messagebox.showerror("Error", "Amount is required.")
            return

        try:
            amt = float(amt_s)
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Amount must be a positive number.")
            return

        try:
            datetime.strptime(date_s, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Invalid date format.")
            return

        category_kind = "income" if ttype == "income" else "expense"
        self.app.category_repo.ensure_category(cat, category_kind)

        # Base transaction dict
        tx: Dict[str, Any] = {
            "type": ttype,
            "category": cat,
            "vendor": (self.var_vendor.get() or "").strip(),
            "amount": amt,
            "date": date_s,
            "description": desc,
            "savings_meta": {
                "move_to_savings": False,
                "spend_from_savings": False,
                "bucket": None,
            },
        }

        is_expense = (ttype == "expense")
        bucket = self.var_bucket.get()

        # --- Savings logic (derived, no compensating income) ---
        if is_expense and self.app.category_repo.is_savings_category(cat):
            # Move to savings
            if self.var_move.get():
                tx["savings_meta"]["move_to_savings"] = True
                tx["savings_meta"]["bucket"] = bucket

        elif is_expense and not self.app.category_repo.is_savings_category(cat):
            # Spend from savings
            if self.var_spend.get():
                # Mark as savings-related spend; repository / services
                # will interpret this correctly (no fake income).
                tx["type"] = "savings_spend"
                tx["savings_meta"]["spend_from_savings"] = True
                tx["savings_meta"]["bucket"] = bucket

        # --- Debt logic (type-aware) ---
        if is_expense and self.var_apply_debt.get():
            debt_id = self._parse_selected_debt_id()
            if debt_id is None:
                messagebox.showerror(
                    "Error",
                    "You checked 'Apply this transaction toward a debt' but no debt is selected.",
                )
                return

            # Determine how this should be typed based on category
            debt_type_for_cat = self._selected_debt_type()

            # Utilities: treat as normal expense applied to a utility debt
            # Credit/Loan payments: treat as dedicated debt_payment
            if debt_type_for_cat in ("credit", "loan"):
                tx["type"] = "debt_payment"

            # Apply payment to the selected debt
            self.debt_repo.apply_payment(debt_id, amt)

        # Save main transaction
        self.tx_repo.add_transaction(tx)

        messagebox.showinfo("Added", "Transaction added.")

        # Reset form
        self.var_amount.set("")
        self.var_vendor.set("")
        self.var_desc.set("")
        self.date_entry.set_date(date.today())
        self.var_move.set(False)
        self.var_spend.set(False)
        self.var_apply_debt.set(False)
        self.var_debt_choice.set("")
        self.pending_debt_id = None

        self._update_savings_ui()
        self._update_debt_ui()
        self._refresh_debt_dropdown()
        self._refresh_vendor_dropdown()

        # Refresh other pages (dashboard, history, savings, debt, etc.)
        self.app.refresh_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """
        Called by App when navigating to this page.

        Used to refresh the debt dropdown (for new/modified debts) and
        to honor any pending_debt_id set by the Debt page.
        """
        if self.var_type.get() == "income":
            self._set_category_choices("income")
        else:
            self._set_category_choices("expense")

        # If we have a pending debt, try to set a sensible default category
        if self.pending_debt_id is not None:
            debts = self.debt_repo.all()
            target = next((d for d in debts if d.id == self.pending_debt_id), None)
            if target is not None:
                d_type = getattr(target, "type", "other")
                debt_name = getattr(target, "name", "").strip()
                exact_match = self.app.category_repo.get(debt_name, "expense", include_inactive=False)
                default_cat = exact_match.name if exact_match and exact_match.debt_type == d_type else self.app.category_repo.default_category_for_debt_type(d_type)
                expense_categories = self._category_names("expense")

                # Force expense mode and set category
                self.var_type.set("expense")
                if default_cat and default_cat in expense_categories:
                    self._set_category_choices("expense", default_cat)
                else:
                    self._set_category_choices("expense", expense_categories[0] if expense_categories else None)

                # Auto-check apply debt
                self.var_apply_debt.set(True)

        self._update_savings_ui()
        self._update_debt_ui()
        self._refresh_debt_dropdown()
        self._refresh_vendor_dropdown()
