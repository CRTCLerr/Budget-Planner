"""
Debt Tracker page for the Budget Planner.

Allows the user to:
- Add new debts (with type: Utility, Credit Card, Loan, Other)
- Apply payments (routed to Add Transaction page)
- Modify existing debts (including type)
- Delete debts

This page mirrors the original UI but is fully modular and powered
by the SQLite data layer, and is now debt-type aware.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, Dict

from ui.widgets import (
    Card,
    ScrollablePage,
    FONT,
    TEXT,
    TEXT_SEC,
    CARD_BG,
    BG,
    PRIMARY,
    PRIMARY_HOVER,
    DANGER,
    SUCCESS,
)
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

if TYPE_CHECKING:
    from ui.app import App


# UI labels → internal debt type codes
DEBT_TYPE_LABEL_TO_CODE: Dict[str, str] = {
    "Utility Bill": "utility",
    "Credit Card": "credit",
    "Loan": "loan",
    "Other": "other",
}

DEBT_TYPE_CODE_TO_LABEL: Dict[str, str] = {
    v: k for k, v in DEBT_TYPE_LABEL_TO_CODE.items()
}


class DebtPage(ScrollablePage):
    """
    Page for managing debts.

    Features:
    - Add debt (with type)
    - Apply payment
    - Modify debt (including type)
    - Delete debt
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

    def _sync_category_for_debt(self, debt_name: str, debt_type: str) -> None:
        """Ensure a matching expense category exists for this debt name."""
        advisor_group = "needs" if debt_type == "utility" else "financial"
        self.app.category_repo.ensure_category(
            debt_name,
            "expense",
            advisor_group=advisor_group,
            debt_type=debt_type,
            is_savings=False,
        )

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = tk.Frame(self.inner, bg=BG)
        pad.pack(fill="both", expand=True, padx=28, pady=20)

        card = Card(pad, padx=16, pady=12)
        card.pack(fill="both", expand=True)

        tk.Label(
            card,
            text="Debt Tracker",
            font=(FONT, 14, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(0, 10))

        # --- Add Debt Form ---
        form = tk.Frame(card, bg=CARD_BG)
        form.pack(fill="x", pady=(0, 10))

        tk.Label(
            form,
            text="Name",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            form,
            text="Amount ($)",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        tk.Label(
            form,
            text="Debt Type",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=2, sticky="w", padx=(10, 0))

        self.var_name = tk.StringVar()
        tk.Entry(
            form,
            textvariable=self.var_name,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            width=24,
        ).grid(row=1, column=0, sticky="w", pady=(2, 4))

        self.var_amount = tk.StringVar()
        tk.Entry(
            form,
            textvariable=self.var_amount,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            width=14,
        ).grid(row=1, column=1, sticky="w", padx=(10, 0))

        self.var_type_label = tk.StringVar(value="Utility Bill")
        self.combo_type = ttk.Combobox(
            form,
            textvariable=self.var_type_label,
            values=list(DEBT_TYPE_LABEL_TO_CODE.keys()),
            state="readonly",
            width=16,
            font=(FONT, 10),
        )
        self.combo_type.grid(row=1, column=2, sticky="w", padx=(10, 0))
        self.combo_type.current(0)

        tk.Button(
            form,
            text="Add Debt",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._add_debt,
        ).grid(row=1, column=3, padx=(10, 0))

        # --- Debt Table ---
        cols = ("name", "type", "original", "remaining")
        table_frame = tk.Frame(card, bg=CARD_BG)
        table_frame.pack(fill="both", expand=True, pady=(8, 4))

        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)
        for c, w, a in [
            ("name", 200, "w"),
            ("type", 120, "w"),
            ("original", 120, "e"),
            ("remaining", 120, "e"),
        ]:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor=a)

        debt_scroll = tk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=debt_scroll.set)
        debt_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # --- Buttons ---
        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.pack(fill="x", pady=(8, 0))

        tk.Button(
            btn_frame,
            text="Apply Payment",
            font=(FONT, 10, "bold"),
            bg=SUCCESS,
            fg="#ffffff",
            activebackground="#15803d",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._apply_payment,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="Modify Selected",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._modify_debt,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_frame,
            text="Delete Selected",
            font=(FONT, 10, "bold"),
            bg=DANGER,
            fg="#ffffff",
            activebackground="#b91c1c",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._delete_debt,
        ).pack(side="left", padx=(8, 0))

    # ------------------------------------------------------------------
    # Refresh Logic
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh the debt table."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        for d in self.debt_repo.all():
            code = getattr(d, "type", "other")
            label = DEBT_TYPE_CODE_TO_LABEL.get(code, "Other")
            self.tree.insert(
                "",
                "end",
                iid=str(d.id),
                values=(
                    d.name,
                    label,
                    f"${d.original:,.2f}",
                    f"${d.remaining:,.2f}",
                ),
            )

    # ------------------------------------------------------------------
    # Add Debt
    # ------------------------------------------------------------------

    def _add_debt(self) -> None:
        name = self.var_name.get().strip()
        amt_s = self.var_amount.get().strip()
        type_label = self.var_type_label.get().strip() or "Other"
        debt_type = DEBT_TYPE_LABEL_TO_CODE.get(type_label, "other")

        if not name or not amt_s:
            messagebox.showerror("Error", "Name and amount are required.")
            return

        try:
            amt = float(amt_s)
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Amount must be a positive number.")
            return

        # DebtRepository.add is expected to accept an optional type argument.
        # Signature: add(name: str, amount: float, debt_type: str = "other")
        self.debt_repo.add(name, amt, debt_type)  # type: ignore[arg-type]
        self._sync_category_for_debt(name, debt_type)

        self.var_name.set("")
        self.var_amount.set("")
        self.var_type_label.set("Utility Bill")
        self.combo_type.current(0)

        self.refresh()
        self.app.refresh_all()

    # ------------------------------------------------------------------
    # Apply Payment
    # ------------------------------------------------------------------

    def _apply_payment(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return

        debt_id = int(sel[0])

        # Redirect to Add Transaction page with debt preselected
        self.app.pages["Add Transaction"].pending_debt_id = debt_id
        self.app.navigate("Add Transaction")

        page = self.app.pages["Add Transaction"]
        page.var_type.set("expense")
        page._update_categories()

        page.var_apply_debt.set(True)
        page._refresh_debt_dropdown()
        page._update_debt_ui()

    # ------------------------------------------------------------------
    # Modify Debt
    # ------------------------------------------------------------------

    def _modify_debt(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return

        debt_id = int(sel[0])
        debt = next((d for d in self.debt_repo.all() if d.id == debt_id), None)
        if not debt:
            return

        # Popup window
        win = tk.Toplevel(self)
        win.title("Modify Debt")
        win.geometry("360x260")
        win.configure(bg=CARD_BG)
        win.grab_set()

        tk.Label(
            win,
            text="Modify Debt",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(pady=(10, 10))

        frm = tk.Frame(win, bg=CARD_BG)
        frm.pack(pady=10)

        # Name
        tk.Label(
            frm,
            text="Name:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        var_name = tk.StringVar(value=debt.name)
        tk.Entry(
            frm,
            textvariable=var_name,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            width=26,
        ).grid(row=1, column=0, pady=(0, 10), columnspan=2, sticky="w")

        # Amount
        tk.Label(
            frm,
            text="New Total ($):",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w")
        var_amt = tk.StringVar(value=str(debt.remaining))
        tk.Entry(
            frm,
            textvariable=var_amt,
            font=(FONT, 10),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            width=26,
        ).grid(row=3, column=0, pady=(0, 10), columnspan=2, sticky="w")

        # Type
        tk.Label(
            frm,
            text="Debt Type:",
            font=(FONT, 10, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=4, column=0, sticky="w")

        current_code = getattr(debt, "type", "other")
        current_label = DEBT_TYPE_CODE_TO_LABEL.get(current_code, "Other")
        var_type_label = tk.StringVar(value=current_label)

        combo_type = ttk.Combobox(
            frm,
            textvariable=var_type_label,
            values=list(DEBT_TYPE_LABEL_TO_CODE.keys()),
            state="readonly",
            width=18,
            font=(FONT, 10),
        )
        combo_type.grid(row=5, column=0, pady=(0, 10), sticky="w")
        try:
            idx = list(DEBT_TYPE_LABEL_TO_CODE.keys()).index(current_label)
            combo_type.current(idx)
        except ValueError:
            combo_type.current(0)

        def save_changes() -> None:
            new_name = var_name.get().strip()
            if not new_name:
                messagebox.showerror("Error", "Name cannot be empty.")
                return

            try:
                new_amt = float(var_amt.get())
                if new_amt <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "New total must be a positive number.")
                return

            new_type_label = var_type_label.get().strip() or "Other"
            new_type_code = DEBT_TYPE_LABEL_TO_CODE.get(new_type_label, "other")

            # DebtRepository.modify is expected to accept an optional type argument.
            # Signature: modify(id: int, new_name: str, new_amount: float, new_type: str | None = None)
            self.debt_repo.modify(debt_id, new_name, new_amt, new_type_code)  # type: ignore[arg-type]
            self._sync_category_for_debt(new_name, new_type_code)

            self.refresh()
            self.app.refresh_all()
            win.destroy()

        tk.Button(
            win,
            text="Save Changes",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=save_changes,
        ).pack(pady=(10, 0))

    # ------------------------------------------------------------------
    # Delete Debt
    # ------------------------------------------------------------------

    def _delete_debt(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return

        if not messagebox.askyesno("Confirm", "Delete selected debt(s)?"):
            return

        for iid in sel:
            self.debt_repo.delete(int(iid))

        self.refresh()
        self.app.refresh_all()
