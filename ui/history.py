"""
History page for the Budget Planner.

Displays all transactions in a sortable table and allows the user
to delete selected transactions.

Now supports:
- Multi-category filtering via dropdown with checkboxes
- Month/year filtering (only values that exist in data)
- Total income / total expenses for the filtered set
- Type filtering (All / Income / Expense / Savings Spend)
- Editing selected transactions (including vendor)
"""

from __future__ import annotations

import ctypes
import os
import tempfile
import textwrap
import tkinter as tk
from tkinter import ttk, messagebox
from typing import TYPE_CHECKING, List, Dict, Optional, Set
from datetime import date, datetime, timedelta
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    from PIL import ImageWin
except Exception:
    ImageWin = None

try:
    import win32con
    import win32print
    import win32ui
except Exception:
    win32con = None
    win32print = None
    win32ui = None

from ui.widgets import Card, ScrollablePage, FONT, TEXT, TEXT_SEC, CARD_BG, BG
from data.transactions import TransactionRepository
from data.debt import DebtRepository
from data.budgets import BudgetRepository
from data.savings import SavingsService

if TYPE_CHECKING:
    from ui.app import App


PD_RETURNDC = 0x00000100
PD_USEDEVMODECOPIESANDCOLLATE = 0x00040000
PD_NOPAGENUMS = 0x00000008
PD_NOSELECTION = 0x00000004


class PRINTDLGW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hDevMode", wintypes.HGLOBAL),
        ("hDevNames", wintypes.HGLOBAL),
        ("hDC", wintypes.HDC),
        ("Flags", wintypes.DWORD),
        ("nFromPage", wintypes.WORD),
        ("nToPage", wintypes.WORD),
        ("nMinPage", wintypes.WORD),
        ("nMaxPage", wintypes.WORD),
        ("nCopies", wintypes.WORD),
        ("hInstance", wintypes.HINSTANCE),
        ("lCustData", wintypes.LPARAM),
        ("lpfnPrintHook", wintypes.LPVOID),
        ("lpfnSetupHook", wintypes.LPVOID),
        ("lpPrintTemplateName", wintypes.LPCWSTR),
        ("lpSetupTemplateName", wintypes.LPCWSTR),
        ("hPrintTemplate", wintypes.HGLOBAL),
        ("hSetupTemplate", wintypes.HGLOBAL),
    ]


class MultiSelectDropdown(tk.Frame):
    """
    A multi-select dropdown with checkboxes, styled to match the app's Card UI.

    - Shows a button (e.g., "Categories")
    - Clicking opens a floating panel (Toplevel) with checkboxes
    - Closes automatically when focus leaves the panel
    - Exposes get_selected() to retrieve selected options
    """

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        options: Optional[List[str]] = None,
    ) -> None:
        super().__init__(parent, bg=CARD_BG)

        self.label_text = label
        self.options: List[str] = options or []
        self.vars: Dict[str, tk.BooleanVar] = {}
        self.dropdown: Optional[tk.Toplevel] = None

        self.button = tk.Button(
            self,
            text=self.label_text,
            font=(FONT, 9),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=self._toggle_dropdown,
        )
        self.button.pack(fill="x")

        self._build_vars()

    def _build_vars(self) -> None:
        self.vars.clear()
        for opt in self.options:
            self.vars[opt] = tk.BooleanVar(value=False)

    def set_options(self, options: List[str]) -> None:
        """Update the available options, preserving selections where possible."""
        old_selected = self.get_selected()
        self.options = options
        self._build_vars()
        for opt in old_selected:
            if opt in self.vars:
                self.vars[opt].set(True)
        self._update_button_label()

    def get_selected(self) -> Set[str]:
        return {opt for opt, var in self.vars.items() if var.get()}

    def _toggle_dropdown(self) -> None:
        if self.dropdown and tk.Toplevel.winfo_exists(self.dropdown):
            self._close_dropdown()
        else:
            self._open_dropdown()

    def _open_dropdown(self) -> None:
        if self.dropdown and tk.Toplevel.winfo_exists(self.dropdown):
            return

        self.dropdown = tk.Toplevel(self)
        self.dropdown.overrideredirect(True)
        self.dropdown.configure(bg=BG)

        # Position below the button
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.dropdown.geometry(f"+{x}+{y}")

        # Card-style container
        container = Card(self.dropdown, padx=8, pady=6)
        container.pack(fill="both", expand=True)

        # Checkboxes
        for opt in self.options:
            cb = tk.Checkbutton(
                container,
                text=opt,
                variable=self.vars[opt],
                font=(FONT, 9),
                fg=TEXT,
                bg=CARD_BG,
                activebackground=CARD_BG,
                anchor="w",
                relief="flat",
                padx=4,
                pady=1,
            )
            cb.pack(fill="x", anchor="w")

        # Close when focus leaves
        self.dropdown.bind("<FocusOut>", lambda e: self._close_dropdown())
        self.dropdown.focus_set()

    def _close_dropdown(self) -> None:
        if self.dropdown and tk.Toplevel.winfo_exists(self.dropdown):
            self.dropdown.destroy()
        self.dropdown = None
        self._update_button_label()

    def _update_button_label(self) -> None:
        selected = self.get_selected()
        if not selected:
            text = self.label_text
        else:
            text = f"{self.label_text} ({len(selected)} selected)"
        self.button.config(text=text)


class HistoryPage(ScrollablePage):
    """
    Page showing the full transaction history.

    Allows:
    - Viewing all transactions
    - Deleting selected transactions
    - Filtering by category (multi-select)
    - Filtering by type
    - Filtering by month/year
    - Seeing total income/expense for the filtered set
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

        self.month_var = tk.StringVar(value="All")
        self.year_var = tk.StringVar(value="All")
        self.report_printer_var = tk.StringVar(value="")

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = tk.Frame(self.inner, bg=BG)
        pad.pack(fill="both", expand=True, padx=28, pady=20)

        card = Card(pad, padx=16, pady=12)
        card.pack(fill="both", expand=True)

        # --------------------------------------------------------------
        # FILTER ROW (LEFT) + TOTALS (RIGHT)
        # --------------------------------------------------------------
        filter_row = tk.Frame(card, bg=CARD_BG)
        filter_row.pack(fill="x", pady=(0, 12))

        # LEFT SIDE: Category + Vendor + Type + Month + Year filters
        left_filters = tk.Frame(filter_row, bg=CARD_BG)
        left_filters.pack(side="left", fill="x")

        # ---------------- CATEGORY DROPDOWN ----------------
        cat_container = tk.Frame(left_filters, bg=CARD_BG)
        cat_container.pack(side="left", padx=(0, 16))

        tk.Label(
            cat_container,
            text="Categories",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).pack(anchor="w")

        self.category_dropdown = MultiSelectDropdown(
            cat_container,
            label="Categories",
            options=[],
        )
        self.category_dropdown.pack(fill="x", pady=(2, 0))

        # ---------------- VENDOR DROPDOWN ----------------
        vendor_container = tk.Frame(left_filters, bg=CARD_BG)
        vendor_container.pack(side="left", padx=(0, 16))

        tk.Label(
            vendor_container,
            text="Vendors",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).pack(anchor="w")

        self.vendor_dropdown = MultiSelectDropdown(
            vendor_container,
            label="Vendors",
            options=[],
        )
        self.vendor_dropdown.pack(fill="x", pady=(2, 0))

        # ---------------- TYPE DROPDOWN ----------------
        type_container = tk.Frame(left_filters, bg=CARD_BG)
        type_container.pack(side="left", padx=(0, 16))

        tk.Label(
            type_container,
            text="Types",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).pack(anchor="w")

        self.type_dropdown = MultiSelectDropdown(
            type_container,
            label="Types",
            options=["Income", "Expense", "Savings Spend", "Debt Payment"],
        )
        self.type_dropdown.pack(fill="x", pady=(2, 0))

        # ---------------- MONTH / YEAR FILTERS ----------------
        date_frame = tk.Frame(left_filters, bg=CARD_BG)
        date_frame.pack(side="left", padx=(0, 16))

        tk.Label(
            date_frame,
            text="Month",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        self.month_cb = ttk.Combobox(
            date_frame,
            textvariable=self.month_var,
            state="readonly",
            width=8,
            values=["All"],
        )
        self.month_cb.grid(row=1, column=0, sticky="w", pady=(0, 4))

        tk.Label(
            date_frame,
            text="Year",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.year_cb = ttk.Combobox(
            date_frame,
            textvariable=self.year_var,
            state="readonly",
            width=8,
            values=["All"],
        )
        self.year_cb.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(0, 4))

        # ---------------- APPLY / CLEAR BUTTONS ----------------
        btn_filter_frame = tk.Frame(left_filters, bg=CARD_BG)
        btn_filter_frame.pack(side="left", padx=(4, 0))

        tk.Button(
            btn_filter_frame,
            text="Apply Filters",
            font=(FONT, 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=self.refresh,
        ).pack(side="top", pady=(0, 4))

        tk.Button(
            btn_filter_frame,
            text="Clear Filters",
            font=(FONT, 9),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=self._clear_filters,
        ).pack(side="top")

        # --------------------------------------------------------------
        # RIGHT SIDE: TOTALS (SIDE-BY-SIDE)
        # --------------------------------------------------------------
        totals_frame = tk.Frame(filter_row, bg=CARD_BG)
        totals_frame.pack(side="right", padx=(10, 0))

        self.total_income_label = tk.Label(
            totals_frame,
            text="Income: $0.00",
            font=(FONT, 10, "bold"),
            fg="#16a34a",
            bg=CARD_BG,
        )
        self.total_income_label.pack(side="left", padx=(0, 12))

        self.total_expense_label = tk.Label(
            totals_frame,
            text="Expenses: $0.00",
            font=(FONT, 10, "bold"),
            fg="#dc2626",
            bg=CARD_BG,
        )
        self.total_expense_label.pack(side="left")

        # --------------------------------------------------------------
        # TREEVIEW (Transaction Table)
        # --------------------------------------------------------------
        cols = ("date", "type", "category", "vendor", "description", "amount")
        table_frame = tk.Frame(card, bg=CARD_BG)
        table_frame.pack(fill="both", expand=True, pady=(4, 8))

        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        for c, w, a in [
            ("date", 100, "w"),
            ("type", 120, "center"),
            ("category", 150, "w"),
            ("vendor", 150, "w"),
            ("description", 220, "w"),
            ("amount", 110, "e"),
        ]:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=w, anchor=a)

        history_scroll = tk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=history_scroll.set)
        history_scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())

        # --------------------------------------------------------------
        # DELETE BUTTON
        # --------------------------------------------------------------
        btn_frame = tk.Frame(card, bg=CARD_BG)
        btn_frame.pack(fill="x", pady=(8, 0))

        tk.Button(
            btn_frame,
            text="Print Report",
            font=(FONT, 10, "bold"),
            bg="#0f766e",
            fg="#ffffff",
            activebackground="#115e59",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._open_report_pdf_preview,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Edit Selected",
            font=(FONT, 10, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._edit_selected,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Delete Selected",
            font=(FONT, 10, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._delete_selected,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Filters helpers
    # ------------------------------------------------------------------

    def _clear_filters(self) -> None:
        self.month_var.set("All")
        self.year_var.set("All")
        # Clear type selections
        for var in self.type_dropdown.vars.values():
            var.set(False)
        self.type_dropdown._update_button_label()
        # Clear category selections
        for var in self.category_dropdown.vars.values():
            var.set(False)
        self.category_dropdown._update_button_label()
        # Clear vendor selections
        for var in self.vendor_dropdown.vars.values():
            var.set(False)
        self.vendor_dropdown._update_button_label()
        self.refresh()

    # ------------------------------------------------------------------
    # Report Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_report_period(period: str) -> str:
        if period in {"month", "quarter", "year", "all"}:
            return period
        return "month"

    @staticmethod
    def _format_currency(value: float) -> str:
        return f"${value:,.2f}"

    @staticmethod
    def _get_report_font(size: int = 28) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_path = r"C:\Windows\Fonts\consola.ttf"
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _available_printers() -> List[str]:
        if win32print is None:
            return []

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = [entry[2] for entry in win32print.EnumPrinters(flags)]

        seen: Set[str] = set()
        unique_printers: List[str] = []
        for printer in printers:
            if printer not in seen:
                seen.add(printer)
                unique_printers.append(printer)
        return unique_printers

    @staticmethod
    def _default_report_printer(printers: List[str]) -> str:
        brother_printers = [printer for printer in printers if "brother" in printer.lower()]
        if brother_printers:
            return brother_printers[0]
        return printers[0] if printers else ""

    @staticmethod
    def _safe_report_date_range(period: str, reference: Optional[date] = None) -> tuple[Optional[date], Optional[date], str]:
        ref = reference or date.today()
        period = HistoryPage._normalize_report_period(period)

        if period == "all":
            return None, None, "All Time"

        if period == "month":
            start = ref.replace(day=1)
            if ref.month == 12:
                end = date(ref.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(ref.year, ref.month + 1, 1) - timedelta(days=1)
            return start, end, ref.strftime("%B %Y")

        if period == "quarter":
            quarter = ((ref.month - 1) // 3) + 1
            start_month = ((quarter - 1) * 3) + 1
            start = date(ref.year, start_month, 1)
            if start_month == 10:
                end = date(ref.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(ref.year, start_month + 3, 1) - timedelta(days=1)
            return start, end, f"Q{quarter} {ref.year}"

        start = date(ref.year, 1, 1)
        end = date(ref.year, 12, 31)
        return start, end, str(ref.year)

    def _transactions_for_report(self, period: str):
        start, end, _ = self._safe_report_date_range(period)
        if start is None or end is None:
            return list(self.tx_repo.all())
        return self.tx_repo.by_date_range(start, end)

    def _report_page_size(self, printer_name: str) -> tuple[int, int]:
        if win32ui is None or win32print is None or not printer_name:
            return 1200, 1550

        dc = None
        try:
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer_name)
            return (
                int(dc.GetDeviceCaps(win32con.HORZRES)),
                int(dc.GetDeviceCaps(win32con.VERTRES)),
            )
        except Exception:
            return 1200, 1550
        finally:
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass

    def _report_printer_dpi(self, printer_name: str) -> int:
        if win32ui is None or win32print is None or win32con is None or not printer_name:
            return 203

        dc = None
        try:
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer_name)
            dpi_x = int(dc.GetDeviceCaps(win32con.LOGPIXELSX))
            dpi_y = int(dc.GetDeviceCaps(win32con.LOGPIXELSY))
            dpi = max(dpi_x, dpi_y)
            return dpi if dpi > 0 else 203
        except Exception:
            return 203
        finally:
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass

    def _render_report_pages(self, report_text: str, printer_name: str) -> List[Image.Image]:
        page_width, page_height = self._report_page_size(printer_name)
        printer_dpi = self._report_printer_dpi(printer_name)
        return self._render_report_pages_for_metrics(report_text, page_width, page_height, printer_dpi)

    def _render_report_pages_for_metrics(
        self,
        report_text: str,
        page_width: int,
        page_height: int,
        printer_dpi: int,
    ) -> List[Image.Image]:
        font_size = max(1, int(printer_dpi * 12 / 72))
        font = self._get_report_font(size=font_size)
        draw_probe = ImageDraw.Draw(Image.new("RGB", (10, 10), "white"))
        line_height = draw_probe.textbbox((0, 0), "Ag", font=font)[3] + max(8, font_size // 5)
        char_width = max(12, draw_probe.textbbox((0, 0), "M", font=font)[2])

        margin_x = max(80, font_size * 2)
        margin_y = max(80, font_size * 2)
        content_width = max(200, page_width - (margin_x * 2))
        max_chars = max(40, content_width // char_width)

        pages: List[Image.Image] = []
        page = Image.new("RGB", (page_width, page_height), "white")
        draw = ImageDraw.Draw(page)
        y = margin_y

        def _new_page() -> None:
            nonlocal page, draw, y
            pages.append(page)
            page = Image.new("RGB", (page_width, page_height), "white")
            draw = ImageDraw.Draw(page)
            y = margin_y

        for raw_line in report_text.splitlines():
            wrapped_lines = textwrap.wrap(
                raw_line,
                width=max_chars,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]

            for line in wrapped_lines:
                if y + line_height > page_height - margin_y:
                    _new_page()
                draw.text((margin_x, y), line, fill="black", font=font)
                y += line_height

        pages.append(page)
        return pages

    def _selected_history_filters(self) -> str:
        parts: List[str] = []

        if self.month_var.get() != "All":
            parts.append(f"Month {self.month_var.get()}")
        if self.year_var.get() != "All":
            parts.append(f"Year {self.year_var.get()}")

        categories = sorted(self.category_dropdown.get_selected())
        vendors = sorted(self.vendor_dropdown.get_selected())
        types = sorted(self.type_dropdown.get_selected())

        if categories:
            parts.append("Categories: " + ", ".join(categories))
        if vendors:
            parts.append("Vendors: " + ", ".join(vendors))
        if types:
            parts.append("Types: " + ", ".join(types))

        return " | ".join(parts) if parts else "All history"

    def _filtered_history_transactions(self) -> List[object]:
        all_txs = list(self.tx_repo.all())
        selected_categories = self.category_dropdown.get_selected()
        selected_vendors = self.vendor_dropdown.get_selected()
        selected_types = self.type_dropdown.get_selected()
        month_filter = self.month_var.get()
        year_filter = self.year_var.get()

        month_filter_val = int(month_filter) if month_filter != "All" else None
        year_filter_val = int(year_filter) if year_filter != "All" else None

        filtered_txs = []
        for t in all_txs:
            dt = self._safe_parse_date(t.date)
            if dt is None:
                continue

            if month_filter_val is not None and dt.month != month_filter_val:
                continue
            if year_filter_val is not None and dt.year != year_filter_val:
                continue

            if selected_categories and t.category not in selected_categories:
                continue

            vendor = (t.vendor or "").strip()
            if selected_vendors and vendor not in selected_vendors:
                continue

            if t.type == "savings_spend":
                display_type = "Savings Spend"
            elif t.type == "debt_payment":
                display_type = "Debt Payment"
            else:
                display_type = t.type.title()

            if selected_types and display_type not in selected_types:
                continue

            filtered_txs.append(t)

        return filtered_txs

    def _build_report_text(self, txs: List[object]) -> str:
        txs = sorted(txs, key=lambda tx: (tx.date, tx.id or 0))

        if self.month_var.get() == "All" and self.year_var.get() == "All":
            period_label = "History Filters"
        else:
            period_label = self._selected_history_filters()

        spending_types = {"expense", "savings_spend", "debt_payment"}
        income_total = sum(t.amount for t in txs if t.type == "income")
        spending_total = sum(t.amount for t in txs if t.type in spending_types)
        net_total = income_total - spending_total

        by_category: Dict[str, float] = {}
        by_vendor: Dict[str, float] = {}
        for tx in txs:
            if tx.type not in spending_types:
                continue
            category = tx.category.strip() or "Uncategorized"
            vendor = (tx.vendor or "").strip() or "Unspecified"
            by_category[category] = by_category.get(category, 0.0) + tx.amount
            by_vendor[vendor] = by_vendor.get(vendor, 0.0) + tx.amount

        lines: List[str] = []
        lines.append("Budget Planner History Report")
        lines.append(f"Filters: {period_label}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("Summary")
        lines.append(f"  Income:   {self._format_currency(income_total)}")
        lines.append(f"  Paid Out: {self._format_currency(spending_total)}")
        lines.append(f"  Net:      {self._format_currency(net_total)}")
        lines.append("")

        lines.append("Paid By Category")
        if by_category:
            for category, total in sorted(by_category.items(), key=lambda item: item[0].lower()):
                lines.append(f"  {category:<24} {self._format_currency(total):>12}")
        else:
            lines.append("  No spending transactions in this period.")
        lines.append("")

        lines.append("Paid By Vendor")
        if by_vendor:
            for vendor, total in sorted(by_vendor.items(), key=lambda item: item[0].lower()):
                lines.append(f"  {vendor:<24} {self._format_currency(total):>12}")
        else:
            lines.append("  No spending transactions in this period.")
        lines.append("")

        lines.append("Transaction Detail")
        if not txs:
            lines.append("  No transactions found for this period.")
        else:
            lines.append("  Date        Type             Category             Vendor               Amount      Description")
            lines.append("  ----------------------------------------------------------------------------")
            for tx in txs:
                if tx.type == "income":
                    display_type = "Income"
                    amount_prefix = "+"
                elif tx.type == "expense":
                    display_type = "Expense"
                    amount_prefix = "-"
                elif tx.type == "savings_spend":
                    display_type = "Savings Spend"
                    amount_prefix = "-"
                elif tx.type == "debt_payment":
                    display_type = "Debt Payment"
                    amount_prefix = "-"
                else:
                    display_type = tx.type.title()
                    amount_prefix = ""

                category = (tx.category or "").strip() or "Uncategorized"
                vendor = (tx.vendor or "").strip() or "Unspecified"
                description = (tx.description or "").strip()
                if len(description) > 40:
                    description = description[:37] + "..."

                lines.append(
                    f"  {tx.date:<10} {display_type:<15} {category:<20} {vendor:<19} {amount_prefix}{tx.amount:>10,.2f}  {description}"
                )

        lines.append("")
        lines.append("Tip: Print this report from the preview window or keep the text file for records.")
        return "\n".join(lines)

    def _open_report_pdf_preview(self) -> None:
        """Open report in the system PDF viewer to use native print preview/settings."""
        report_text = self._build_report_text(self._filtered_history_transactions())
        printer_name = self.report_printer_var.get().strip()
        if not printer_name:
            printer_name = self._default_report_printer(self._available_printers())

        pages = self._render_report_pages(report_text, printer_name)
        if not pages:
            messagebox.showerror("Print Report", "No report pages were generated.")
            return

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
                pdf_path = handle.name

            dpi = self._report_printer_dpi(printer_name)
            rgb_pages = [page.convert("RGB") for page in pages]
            first_page, extra_pages = rgb_pages[0], rgb_pages[1:]
            first_page.save(
                pdf_path,
                format="PDF",
                save_all=True,
                append_images=extra_pages,
                resolution=max(72, dpi),
            )
            os.startfile(pdf_path)
        except Exception as exc:
            messagebox.showerror("Print Report", f"Could not open native print preview: {exc}")

    def _print_report_with_windows_dialog(self) -> None:
        """Open native Windows print dialog and print the filtered History report."""
        if win32ui is None or win32con is None or ImageWin is None:
            messagebox.showerror("Print Report", "Windows print support is not available.")
            return

        report_text = self._build_report_text(self._filtered_history_transactions())
        print_dlg = PRINTDLGW()
        print_dlg.lStructSize = ctypes.sizeof(PRINTDLGW)
        print_dlg.hwndOwner = int(self.winfo_toplevel().winfo_id())
        # Keep flags minimal so Windows/printer driver can expose full settings.
        print_dlg.Flags = PD_RETURNDC | PD_USEDEVMODECOPIESANDCOLLATE

        comdlg32 = ctypes.windll.comdlg32
        if not comdlg32.PrintDlgW(ctypes.byref(print_dlg)):
            err = comdlg32.CommDlgExtendedError()
            if err != 0:
                messagebox.showerror("Print Report", f"Windows print dialog failed (code {err}).")
            return

        dc = None
        try:
            if not print_dlg.hDC:
                messagebox.showerror("Print Report", "No printer device was returned by Windows.")
                return

            dc = win32ui.CreateDCFromHandle(int(print_dlg.hDC))

            page_width = int(dc.GetDeviceCaps(win32con.HORZRES))
            page_height = int(dc.GetDeviceCaps(win32con.VERTRES))
            dpi_x = int(dc.GetDeviceCaps(win32con.LOGPIXELSX))
            dpi_y = int(dc.GetDeviceCaps(win32con.LOGPIXELSY))
            printer_dpi = max(dpi_x, dpi_y) if max(dpi_x, dpi_y) > 0 else 203

            pages = self._render_report_pages_for_metrics(
                report_text,
                page_width,
                page_height,
                printer_dpi,
            )

            dc.StartDoc("Budget Planner History Report")
            dib_pages = [ImageWin.Dib(page) for page in pages]

            for dib in dib_pages:
                dc.StartPage()
                dib.draw(dc.GetHandleOutput(), (0, 0, page_width, page_height))
                dc.EndPage()

            dc.EndDoc()
        except Exception as exc:
            messagebox.showerror("Print Report", f"Could not print report: {exc}")
        finally:
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass
            if print_dlg.hDevMode:
                ctypes.windll.kernel32.GlobalFree(print_dlg.hDevMode)
            if print_dlg.hDevNames:
                ctypes.windll.kernel32.GlobalFree(print_dlg.hDevNames)

    def _write_report_tempfile(self, report_text: str) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8", newline="\n") as handle:
            handle.write(report_text)
            return handle.name

    def _print_report_pages(self, pages: List[Image.Image], printer_name: str) -> None:
        if not printer_name:
            messagebox.showerror("Print Report", "Choose a printer before printing the report.")
            return

        if win32ui is None or win32print is None or win32con is None or ImageWin is None:
            report_text = "\n".join(self._build_report_text(self._filtered_history_transactions()).splitlines())
            report_path = self._write_report_tempfile(report_text)
            try:
                os.startfile(report_path, "printto", printer_name)
                return
            except Exception as exc:
                messagebox.showwarning(
                    "Print Report",
                    f"The report was created at:\n{report_path}\n\nAutomatic printing failed: {exc}",
                )
                return

        dc = None
        try:
            dc = win32ui.CreateDC()
            dc.CreatePrinterDC(printer_name)
            page_width = int(dc.GetDeviceCaps(win32con.HORZRES))
            page_height = int(dc.GetDeviceCaps(win32con.VERTRES))

            dc.StartDoc("Budget Planner History Report")
            dib_pages = [ImageWin.Dib(page) for page in pages]

            for dib in dib_pages:
                dc.StartPage()
                dib.draw(dc.GetHandleOutput(), (0, 0, page_width, page_height))
                dc.EndPage()

            dc.EndDoc()
        except Exception as exc:
            messagebox.showerror("Print Report", f"Unable to print to {printer_name}: {exc}")
        finally:
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass

    def _show_report_preview(self) -> None:
        report_text = self._build_report_text(self._filtered_history_transactions())
        printer_name = self.report_printer_var.get().strip()
        pages = self._render_report_pages(report_text, printer_name)

        preview = tk.Toplevel(self)
        preview.title("History Report Preview")
        preview.configure(bg=CARD_BG)
        preview.transient(self.winfo_toplevel())
        preview.grab_set()
        preview.geometry("980x720")

        wrap = tk.Frame(preview, bg=CARD_BG, padx=14, pady=12)
        wrap.pack(fill="both", expand=True)

        header = tk.Frame(wrap, bg=CARD_BG)
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text="History Report Preview",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(side="left")

        tk.Button(
            header,
            text="Print",
            font=(FONT, 10, "bold"),
            bg="#0f766e",
            fg="#ffffff",
            activebackground="#115e59",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=lambda: self._print_report_pages(pages, self.report_printer_var.get().strip()),
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            header,
            text="Open As Text",
            font=(FONT, 10),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=lambda: os.startfile(self._write_report_tempfile(report_text)),
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            header,
            text="Close",
            font=(FONT, 10),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=preview.destroy,
        ).pack(side="right")

        preview_canvas = tk.Canvas(wrap, bg="#dbe2ea", highlightthickness=0)
        preview_v_scroll = tk.Scrollbar(wrap, orient="vertical", command=preview_canvas.yview)
        preview_h_scroll = tk.Scrollbar(wrap, orient="horizontal", command=preview_canvas.xview)
        preview_canvas.configure(yscrollcommand=preview_v_scroll.set, xscrollcommand=preview_h_scroll.set)

        preview_v_scroll.pack(side="right", fill="y")
        preview_h_scroll.pack(side="bottom", fill="x")
        preview_canvas.pack(side="left", fill="both", expand=True)

        pages_frame = tk.Frame(preview_canvas, bg="#dbe2ea")
        preview_canvas.create_window((20, 20), window=pages_frame, anchor="nw")

        self._report_preview_images = [ImageTk.PhotoImage(page) for page in pages]

        for index, page_image in enumerate(self._report_preview_images, start=1):
            page_container = tk.Frame(pages_frame, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
            page_container.pack(fill="both", expand=False, pady=(0, 18))

            tk.Label(page_container, image=page_image, bg="#ffffff").pack()
            tk.Label(
                page_container,
                text=f"Page {index}",
                font=(FONT, 9),
                fg=TEXT_SEC,
                bg="#ffffff",
            ).pack(anchor="e", padx=10, pady=(0, 8))

        def _update_preview_scrollregion(_event=None) -> None:
            preview_canvas.configure(scrollregion=preview_canvas.bbox("all"))

        pages_frame.bind("<Configure>", _update_preview_scrollregion)
        preview_canvas.bind("<Configure>", _update_preview_scrollregion)

    def _open_report_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Print History Report")
        dialog.configure(bg=CARD_BG)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)

        wrap = tk.Frame(dialog, bg=CARD_BG, padx=16, pady=14)
        wrap.pack(fill="both", expand=True)

        tk.Label(
            wrap,
            text="History Report",
            font=(FONT, 12, "bold"),
            fg=TEXT,
            bg=CARD_BG,
        ).pack(anchor="w")

        tk.Label(
            wrap,
            text="Uses the same filters currently applied in History.",
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).pack(anchor="w", pady=(2, 10))

        printer_options = self._available_printers()
        default_printer = self._default_report_printer(printer_options)
        if not printer_options:
            messagebox.showerror("Print Report", "No printers were found on this computer.")
            dialog.destroy()
            return

        self.report_printer_var.set(default_printer)

        printer_frame = tk.Frame(wrap, bg=CARD_BG)
        printer_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            printer_frame,
            text="Printer",
            font=(FONT, 9, "bold"),
            fg=TEXT_SEC,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        printer_combo = ttk.Combobox(
            printer_frame,
            textvariable=self.report_printer_var,
            values=printer_options,
            state="readonly",
            width=42,
        )
        printer_combo.grid(row=1, column=0, sticky="w")

        btns = tk.Frame(wrap, bg=CARD_BG)
        btns.pack(fill="x", pady=(14, 0))

        tk.Button(
            btns,
            text="Preview",
            font=(FONT, 10, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._show_report_preview,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btns,
            text="Print Now",
            font=(FONT, 10, "bold"),
            bg="#0f766e",
            fg="#ffffff",
            activebackground="#115e59",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._open_report_pdf_preview,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btns,
            text="Open As Text",
            font=(FONT, 10),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=lambda: os.startfile(
                self._write_report_tempfile(self._build_report_text(self._filtered_history_transactions()))
            ),
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btns,
            text="Cancel",
            font=(FONT, 10),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=dialog.destroy,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Refresh Logic
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_parse_date(s: str):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    def refresh(self) -> None:
        """Refresh the history table from SQLite, applying filters."""
        # Clear table
        for row in self.tree.get_children():
            self.tree.delete(row)

        all_txs = list(self.tx_repo.all())

        # Build category list from configured categories plus used values
        categories = sorted(
            set(self.app.category_repo.names())
            | {t.category for t in all_txs if t.category}
        )
        self.category_dropdown.set_options(categories)

        # Build vendor list from data
        vendors = sorted({(t.vendor or "").strip() for t in all_txs if (t.vendor or "").strip()})
        self.vendor_dropdown.set_options(vendors)

        # Build month/year lists from data
        dates = [self._safe_parse_date(t.date) for t in all_txs]
        dates = [d for d in dates if d is not None]

        months = sorted({d.month for d in dates})
        years = sorted({d.year for d in dates})

        month_values = ["All"] + [f"{m:02d}" for m in months]
        year_values = ["All"] + [str(y) for y in years]

        self.month_cb["values"] = month_values
        self.year_cb["values"] = year_values

        if self.month_var.get() not in month_values:
            self.month_var.set("All")
        if self.year_var.get() not in year_values:
            self.year_var.set("All")

        filtered_txs = self._filtered_history_transactions()

        total_income = 0.0
        total_expense = 0.0

        # Apply filters and populate rows
        for t in filtered_txs:
            vendor = (t.vendor or "").strip()
            if t.type == "savings_spend":
                display_type = "Savings Spend"
            elif t.type == "debt_payment":
                display_type = "Debt Payment"
            else:
                display_type = t.type.title()

            # Amount + totals
            if t.type == "income":
                sign = "+"
                total_income += t.amount
            elif t.type in ("expense", "savings_spend"):
                sign = "-"
                total_expense += t.amount
            elif t.type == "debt_payment":
                sign = "-"
                total_expense += t.amount
            else:
                sign = ""

            amount_str = f"{sign}${t.amount:,.2f}"

            self.tree.insert(
                "",
                "end",
                iid=str(t.id),
                values=(
                    t.date,
                    display_type,
                    t.category,
                    vendor,
                    t.description,
                    amount_str,
                ),
            )

        # Update totals labels
        self.total_income_label.config(text=f"Income: ${total_income:,.2f}")
        self.total_expense_label.config(text=f"Expenses: ${total_expense:,.2f}")

    # ------------------------------------------------------------------
    # Edit Logic
    # ------------------------------------------------------------------

    def _edit_selected(self) -> None:
        """Open edit dialog for the selected transaction."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Edit Transaction", "Select one transaction to edit.")
            return
        if len(sel) > 1:
            messagebox.showinfo("Edit Transaction", "Please select only one transaction to edit.")
            return

        tx_id = int(sel[0])
        tx = self.tx_repo.get(tx_id)
        if tx is None:
            messagebox.showerror("Error", "Transaction no longer exists.")
            self.refresh()
            return

        dlg = tk.Toplevel(self)
        dlg.title("Edit Transaction")
        dlg.configure(bg=CARD_BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.resizable(False, False)

        wrap = tk.Frame(dlg, bg=CARD_BG, padx=14, pady=12)
        wrap.pack(fill="both", expand=True)

        display_to_value = {
            "Income": "income",
            "Expense": "expense",
            "Savings Spend": "savings_spend",
            "Debt Payment": "debt_payment",
        }
        value_to_display = {v: k for k, v in display_to_value.items()}

        var_type = tk.StringVar(value=value_to_display.get(tx.type, tx.type.title()))
        var_category = tk.StringVar(value=tx.category)
        var_vendor = tk.StringVar(value=tx.vendor)
        var_amount = tk.StringVar(value=f"{tx.amount:.2f}")
        var_date = tk.StringVar(value=tx.date)
        var_desc = tk.StringVar(value=tx.description)

        initial_kind = "income" if tx.type == "income" else "expense"
        categories = sorted(set(self.app.category_repo.names(initial_kind)) | {tx.category})
        vendors = self.tx_repo.vendor_suggestions()

        row = 0

        tk.Label(wrap, text="Type", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        type_combo = ttk.Combobox(
            wrap,
            textvariable=var_type,
            values=list(display_to_value.keys()),
            state="readonly",
            width=32,
            font=(FONT, 10),
        )
        type_combo.grid(row=row, column=0, sticky="w", pady=(0, 10))
        row += 1

        tk.Label(wrap, text="Category", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        category_combo = ttk.Combobox(
            wrap,
            textvariable=var_category,
            values=categories,
            state="normal",
            width=32,
            font=(FONT, 10),
        )
        category_combo.grid(row=row, column=0, sticky="w", pady=(0, 10))
        row += 1

        def _refresh_category_choices() -> None:
            selected_type = display_to_value.get(var_type.get().strip(), "expense")
            kind = "income" if selected_type == "income" else "expense"
            values = sorted(set(self.app.category_repo.names(kind)) | {var_category.get().strip()})
            category_combo.configure(values=values)

        type_combo.bind("<<ComboboxSelected>>", lambda e: _refresh_category_choices())

        tk.Label(wrap, text="Vendor / Source", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Combobox(
            wrap,
            textvariable=var_vendor,
            values=vendors,
            state="normal",
            width=32,
            font=(FONT, 10),
        ).grid(row=row, column=0, sticky="w", pady=(0, 10))
        row += 1

        tk.Label(wrap, text="Amount", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        tk.Entry(wrap, textvariable=var_amount, width=35, font=(FONT, 10)).grid(row=row, column=0, sticky="w", pady=(0, 10), ipady=3)
        row += 1

        tk.Label(wrap, text="Date (YYYY-MM-DD)", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        tk.Entry(wrap, textvariable=var_date, width=35, font=(FONT, 10)).grid(row=row, column=0, sticky="w", pady=(0, 10), ipady=3)
        row += 1

        tk.Label(wrap, text="Description", font=(FONT, 9, "bold"), bg=CARD_BG, fg=TEXT_SEC).grid(row=row, column=0, sticky="w")
        row += 1
        tk.Entry(wrap, textvariable=var_desc, width=35, font=(FONT, 10)).grid(row=row, column=0, sticky="w", pady=(0, 12), ipady=3)

        def _save_edit() -> None:
            type_display = var_type.get().strip()
            category = var_category.get().strip()
            vendor = var_vendor.get().strip()
            amount_s = var_amount.get().strip()
            date_s = var_date.get().strip()
            desc = var_desc.get().strip()

            if type_display not in display_to_value:
                messagebox.showerror("Error", "Select a valid transaction type.")
                return
            if not category:
                messagebox.showerror("Error", "Category is required.")
                return

            selected_type = display_to_value[type_display]
            category_kind = "income" if selected_type == "income" else "expense"
            configured_category = self.app.category_repo.get(category, category_kind, include_inactive=True)
            if configured_category is None:
                self.app.category_repo.ensure_category(category, category_kind)
            elif configured_category.active is False and category != tx.category:
                self.app.category_repo.ensure_category(category, category_kind)

            try:
                amount = float(amount_s)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Amount must be a positive number.")
                return

            try:
                datetime.strptime(date_s, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Error", "Date must be in YYYY-MM-DD format.")
                return

            ok = self.tx_repo.update_transaction(
                tx_id,
                {
                    "type": selected_type,
                    "category": category,
                    "vendor": vendor,
                    "amount": amount,
                    "date": date_s,
                    "description": desc,
                },
            )
            if not ok:
                messagebox.showerror("Error", "Could not update this transaction.")
                return

            dlg.destroy()
            self.refresh()
            self.app.refresh_all()

        btns = tk.Frame(wrap, bg=CARD_BG)
        btns.grid(row=row + 1, column=0, sticky="w")

        tk.Button(
            btns,
            text="Save",
            font=(FONT, 10, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=_save_edit,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btns,
            text="Cancel",
            font=(FONT, 10),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=dlg.destroy,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Delete Logic
    # ------------------------------------------------------------------

    def _delete_selected(self) -> None:
        """Delete selected transactions from the database."""
        sel = self.tree.selection()
        if not sel:
            return

        if not messagebox.askyesno("Confirm", "Delete selected transaction(s)?"):
            return

        for iid in sel:
            tid = int(iid)
            self.tx_repo.delete(tid)

        # Refresh this page + all others (dashboard, savings, etc.)
        self.refresh()
        self.app.refresh_all()
