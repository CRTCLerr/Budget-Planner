"""
Reusable Tkinter UI widgets for the Budget Planner application.

This module provides:
- Card: a styled container frame
- StatCard: a card with a title and large numeric value
- SidebarButton: navigation button for the sidebar
- CalendarPopup: a dropdown calendar widget
- DateEntry: an entry field with a calendar button

All widgets are visually identical to the original monolithic app,
but internally cleaner, modular, and easier to maintain.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# Shared UI Constants (identical to original)
# ---------------------------------------------------------------------------

SIDEBAR_BG = "#1e293b"
SIDEBAR_HOVER = "#334155"
SIDEBAR_ACTIVE = "#2563eb"

BG = "#f1f5f9"
CARD_BG = "#ffffff"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
SUCCESS = "#16a34a"
DANGER = "#dc2626"
WARNING = "#f59e0b"
TEXT = "#0f172a"
TEXT_SEC = "#64748b"
BORDER = "#e2e8f0"

CAL_HEADER = "#1e40af"
CAL_TODAY = "#dbeafe"
CAL_SELECTED = "#2563eb"

FONT = "Segoe UI"


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

class Card(tk.Frame):
    """
    A reusable card-style container with padding and border.

    Visually identical to the original app, but implemented cleanly.
    """

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("bg", CARD_BG)
        kwargs.setdefault("highlightbackground", BORDER)
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("padx", 20)
        kwargs.setdefault("pady", 16)
        super().__init__(parent, **kwargs)


class ScrollablePage(tk.Frame):
    """
    A generic scrollable page container.

    Provides a vertical scrollbar and a reusable inner frame that tracks
    its scrollregion automatically.
    """

    def __init__(self, parent: tk.Widget, bg: str = BG, **kwargs) -> None:
        super().__init__(parent, bg=bg, **kwargs)

        self._scroll_canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self._scrollbar = tk.Scrollbar(self, orient="vertical", command=self._scroll_canvas.yview)
        self._scrollbar.pack(side="right", fill="y")

        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        self.inner = tk.Frame(self._scroll_canvas, bg=bg)
        self._inner_id = self._scroll_canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, event: tk.Event) -> None:
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._scroll_canvas.itemconfig(self._inner_id, width=event.width)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self) -> None:
        bbox = self._scroll_canvas.bbox("all") or (0, 0, 0, 0)
        canvas_height = self._scroll_canvas.winfo_height()
        if canvas_height <= 1:
            return

        content_height = bbox[3] - bbox[1]
        if content_height > canvas_height:
            if not self._scrollbar.winfo_ismapped():
                self._scrollbar.pack(side="right", fill="y")
                self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)
        else:
            if self._scrollbar.winfo_ismapped():
                self._scrollbar.pack_forget()
                self._scroll_canvas.configure(yscrollcommand=lambda *args: None)
            self._scroll_canvas.yview_moveto(0)

    def _can_widget_scroll(self, widget: tk.Widget, delta: int) -> bool:
        if widget is self._scroll_canvas or widget is self.inner or widget is self:
            return False

        current = widget
        while current is not None:
            if current is self._scroll_canvas or current is self.inner or current is self:
                break

            try:
                view = current.yview()
            except Exception:
                current = getattr(current, "master", None)
                continue

            if not isinstance(view, tuple) or len(view) != 2:
                return False

            first, last = view
            if delta > 0 and first > 0:
                return True
            if delta < 0 and last < 1:
                return True
            return False

        return False

    def _is_combobox_popup_widget(self, widget: tk.Widget) -> bool:
        """Return True when wheel input originates from a combobox/list popup."""
        current = widget
        while current is not None:
            try:
                widget_class = current.winfo_class()
            except Exception:
                widget_class = ""

            if widget_class in {"TCombobox", "Combobox", "Listbox", "TComboboxListbox"}:
                return True

            try:
                widget_path = str(current).lower()
            except Exception:
                widget_path = ""
            if "combobox" in widget_path and "popdown" in widget_path:
                return True

            current = getattr(current, "master", None)

        return False

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        # Let combobox dropdown popups handle their own wheel scrolling.
        if self._is_combobox_popup_widget(event.widget):
            return None

        delta = int(event.delta / 120)
        if delta == 0:
            return None

        if self._can_widget_scroll(event.widget, delta):
            return None

        self._scroll_canvas.yview_scroll(-delta, "units")
        return "break"

    def activate_mousewheel(self) -> None:
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def deactivate_mousewheel(self) -> None:
        self._scroll_canvas.unbind_all("<MouseWheel>")

    def scroll_widget_into_view(self, widget: tk.Widget, padding: int = 24) -> None:
        """Scroll the page so the requested widget is visible."""
        if widget is None:
            return

        self.update_idletasks()
        self._scroll_canvas.update_idletasks()

        try:
            inner_top = self.inner.winfo_rooty()
            widget_top = widget.winfo_rooty() - inner_top
            widget_bottom = widget_top + widget.winfo_height()
        except Exception:
            return

        bbox = self._scroll_canvas.bbox(self._inner_id)
        if not bbox:
            return

        content_height = max(1, bbox[3] - bbox[1])
        canvas_height = max(1, self._scroll_canvas.winfo_height())
        view_top = self._scroll_canvas.canvasy(0)
        view_bottom = view_top + canvas_height

        target_top = max(0, widget_top - padding)
        target_bottom = min(content_height, widget_bottom + padding)

        if target_top < view_top:
            self._scroll_canvas.yview_moveto(target_top / max(1, content_height - canvas_height))
        elif target_bottom > view_bottom:
            self._scroll_canvas.yview_moveto(max(0, target_bottom - canvas_height) / max(1, content_height - canvas_height))

        self.update_idletasks()


# ---------------------------------------------------------------------------
# StatCard
# ---------------------------------------------------------------------------

class StatCard(Card):
    """
    A card displaying a title and a large numeric value.

    Used on the dashboard for:
    - Monthly Income
    - Monthly Expenses
    - This Week Spent
    - Total Debt
    - Running Total
    - Total Savings
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        variable: tk.StringVar,
        color: str,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.configure(padx=22, pady=18)

        tk.Label(
            self,
            text=title,
            font=(FONT, 9),
            fg=TEXT_SEC,
            bg=CARD_BG,
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            self,
            textvariable=variable,
            font=(FONT, 24, "bold"),
            fg=color,
            bg=CARD_BG,
            anchor="w",
        ).pack(fill="x", pady=(4, 0))


# ---------------------------------------------------------------------------
# SidebarButton
# ---------------------------------------------------------------------------

class SidebarButton(tk.Frame):
    """
    A navigation button for the sidebar.

    Handles hover, active state, and click behavior.
    """

    def __init__(
        self,
        parent: tk.Widget,
        icon: str,
        label: str,
        command: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=SIDEBAR_BG, cursor="hand2", **kwargs)

        self._active = False
        self._command = command

        self.icon_label = tk.Label(
            self,
            text=icon,
            font=(FONT, 14),
            fg="#94a3b8",
            bg=SIDEBAR_BG,
            width=3,
        )
        self.icon_label.pack(side="left", padx=(16, 4))

        self.text_label = tk.Label(
            self,
            text=label,
            font=(FONT, 11),
            fg="#cbd5e1",
            bg=SIDEBAR_BG,
            anchor="w",
        )
        self.text_label.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self.indicator = tk.Frame(self, bg=SIDEBAR_BG, width=4)
        self.indicator.pack(side="left", fill="y")

        # Bind events
        for widget in (self, self.icon_label, self.text_label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_click)

    # --- State Management ----------------------------------------------------

    def set_active(self, active: bool) -> None:
        """Set this button as active or inactive."""
        self._active = active

        bg = SIDEBAR_ACTIVE if active else SIDEBAR_BG
        fg = "#ffffff" if active else "#cbd5e1"
        icon_fg = "#ffffff" if active else "#94a3b8"
        ind_bg = "#ffffff" if active else SIDEBAR_BG

        for widget in (self, self.icon_label, self.text_label):
            widget.configure(bg=bg)

        self.text_label.configure(fg=fg)
        self.icon_label.configure(fg=icon_fg)
        self.indicator.configure(bg=ind_bg)

    # --- Event Handlers ------------------------------------------------------

    def _on_enter(self, event: tk.Event) -> None:
        if not self._active:
            for widget in (self, self.icon_label, self.text_label):
                widget.configure(bg=SIDEBAR_HOVER)

    def _on_leave(self, event: tk.Event) -> None:
        if not self._active:
            for widget in (self, self.icon_label, self.text_label):
                widget.configure(bg=SIDEBAR_BG)

    def _on_click(self, event: tk.Event) -> None:
        self._command()


# ---------------------------------------------------------------------------
# CalendarPopup
# ---------------------------------------------------------------------------

class CalendarPopup(tk.Toplevel):
    """
    A dropdown calendar widget used by DateEntry.

    Identical appearance to the original, but rewritten cleanly.
    """

    def __init__(
        self,
        parent: tk.Widget,
        selected_date: date,
        callback: Callable[[date], None],
    ) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)

        self._callback = callback
        self._selected = selected_date
        self._year = selected_date.year
        self._month = selected_date.month

        self._build()
        self._position(parent)

        self.grab_set()
        self.bind("<FocusOut>", lambda e: self._maybe_close())
        self.focus_set()

    # --- Layout --------------------------------------------------------------

    def _position(self, anchor: tk.Widget) -> None:
        anchor.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        self.geometry(f"+{x}+{y}")

    def _build(self) -> None:
        """Build the calendar UI."""
        for child in self.winfo_children():
            child.destroy()

        # Header
        header = tk.Frame(self, bg=CAL_HEADER)
        header.pack(fill="x")

        btn_style = dict(
            font=(FONT, 12, "bold"),
            fg="#ffffff",
            bg=CAL_HEADER,
            activebackground=PRIMARY_HOVER,
            activeforeground="#ffffff",
            bd=0,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
        )

        tk.Button(header, text="◀", command=self._prev_month, **btn_style).pack(side="left")

        self.header_label = tk.Label(
            header,
            text=f"{calendar.month_name[self._month]} {self._year}",
            font=(FONT, 11, "bold"),
            fg="#ffffff",
            bg=CAL_HEADER,
        )
        self.header_label.pack(side="left", fill="x", expand=True)

        tk.Button(header, text="▶", command=self._next_month, **btn_style).pack(side="right")

        # Days of week
        dow_frame = tk.Frame(self, bg=CARD_BG)
        dow_frame.pack(fill="x", padx=6, pady=(6, 0))

        for d in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"):
            tk.Label(
                dow_frame,
                text=d,
                font=(FONT, 9, "bold"),
                fg=TEXT_SEC,
                bg=CARD_BG,
                width=4,
            ).pack(side="left", padx=1)

        # Calendar grid
        grid = tk.Frame(self, bg=CARD_BG)
        grid.pack(fill="both", padx=6, pady=(2, 8))

        today = date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self._year, self._month)

        for week in weeks:
            row = tk.Frame(grid, bg=CARD_BG)
            row.pack(fill="x")

            for day_num in week:
                if day_num == 0:
                    tk.Label(row, text="", width=4, bg=CARD_BG).pack(side="left", padx=1, pady=1)
                    continue

                d = date(self._year, self._month, day_num)
                is_today = d == today
                is_selected = d == self._selected

                if is_selected:
                    bg, fg = CAL_SELECTED, "#ffffff"
                elif is_today:
                    bg, fg = CAL_TODAY, PRIMARY
                else:
                    bg, fg = CARD_BG, TEXT

                lbl = tk.Label(
                    row,
                    text=str(day_num),
                    width=4,
                    font=(FONT, 10, "bold" if is_today or is_selected else ""),
                    fg=fg,
                    bg=bg,
                    cursor="hand2",
                )
                lbl.pack(side="left", padx=1, pady=1)

                lbl.bind("<Button-1>", lambda e, dn=day_num: self._pick(dn))
                lbl.bind("<Enter>", lambda e, l=lbl, s=is_selected: l.configure(bg=PRIMARY_HOVER, fg="#ffffff") if not s else None)
                lbl.bind("<Leave>", lambda e, l=lbl, s=is_selected, b=bg, f=fg: l.configure(bg=b, fg=f) if not s else None)

        # Today button
        footer = tk.Frame(self, bg=CARD_BG)
        footer.pack(fill="x", padx=6, pady=(0, 6))

        today_btn = tk.Label(
            footer,
            text="Today",
            font=(FONT, 9, "bold"),
            fg=PRIMARY,
            bg=CARD_BG,
            cursor="hand2",
        )
        today_btn.pack()
        today_btn.bind("<Button-1>", lambda e: self._pick_today())

    # --- Month Navigation -----------------------------------------------------

    def _prev_month(self) -> None:
        if self._month == 1:
            self._month = 12
            self._year -= 1
        else:
            self._month -= 1
        self._build()

    def _next_month(self) -> None:
        if self._month == 12:
            self._month = 1
            self._year += 1
        else:
            self._month += 1
        self._build()

    # --- Selection ------------------------------------------------------------

    def _pick(self, day_num: int) -> None:
        picked = date(self._year, self._month, day_num)
        self._callback(picked)
        self.destroy()

    def _pick_today(self) -> None:
        self._callback(date.today())
        self.destroy()

    # --- Closing --------------------------------------------------------------

    def _maybe_close(self) -> None:
        try:
            focus = self.focus_get()
            if focus is None or not str(focus).startswith(str(self)):
                self.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# DateEntry
# ---------------------------------------------------------------------------

class DateEntry(tk.Frame):
    """
    A date entry widget with a calendar popup button.

    Identical appearance to the original, but rewritten cleanly.
    """

    def __init__(
        self,
        parent: tk.Widget,
        initial_date: Optional[date] = None,
        bg_color: str = CARD_BG,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=bg_color, **kwargs)

        self._date = initial_date or date.today()
        self._popup: Optional[CalendarPopup] = None

        self.var = tk.StringVar(value=self._date.strftime("%Y-%m-%d"))

        self.entry = tk.Entry(
            self,
            textvariable=self.var,
            font=(FONT, 11),
            bg="#f8fafc",
            fg=TEXT,
            relief="solid",
            bd=1,
            highlightthickness=0,
            width=14,
        )
        self.entry.pack(side="left", ipady=5)

        self.btn = tk.Button(
            self,
            text="📅",
            font=(FONT, 12),
            bg=bg_color,
            fg=PRIMARY,
            activebackground=bg_color,
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self._open_popup,
        )
        self.btn.pack(side="left", padx=(4, 0))

    # --- Popup Handling -------------------------------------------------------

    def _open_popup(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return

        try:
            d = datetime.strptime(self.var.get(), "%Y-%m-%d").date()
        except ValueError:
            d = date.today()

        self._popup = CalendarPopup(self, d, self._on_pick)

    def _on_pick(self, picked: date) -> None:
        self._date = picked
        self.var.set(picked.strftime("%Y-%m-%d"))
        self._popup = None

    # --- Public API -----------------------------------------------------------

    def get_date_str(self) -> str:
        """Return the selected date as YYYY-MM-DD."""
        return self.var.get()

    def set_date(self, d: date) -> None:
        """Set the date programmatically."""
        self._date = d
        self.var.set(d.strftime("%Y-%m-%d"))
