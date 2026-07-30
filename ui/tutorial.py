"""Guided tutorial overlay for the Budget Planner application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

import tkinter as tk

from core.app_settings import AppSettings, save_settings
from ui.widgets import CARD_BG, FONT, TEXT, TEXT_SEC, PRIMARY, Card

if TYPE_CHECKING:
    from ui.app import App


@dataclass(frozen=True)
class TutorialStep:
    page_name: str
    title: str
    body: str
    target: Callable[["App"], tk.Widget | None]
    prepare: Callable[["App"], None] | None = None


class TutorialOverlay(tk.Toplevel):
    """A modal overlay that dims the app and spotlights a focused area."""

    def __init__(self, app: "App", on_next: Callable[[], None], on_back: Callable[[], None], on_skip: Callable[[], None]) -> None:
        super().__init__(app)
        self.app = app
        self._on_next = on_next
        self._on_back = on_back
        self._on_skip = on_skip
        self._transparent_key = "#ff00ff"
        self._supports_transparency = True

        self.overrideredirect(True)
        self.transient(app)
        self.attributes("-topmost", True)

        try:
            self.configure(bg=self._transparent_key)
            self.wm_attributes("-transparentcolor", self._transparent_key)
        except tk.TclError:
            self._supports_transparency = False
            self.configure(bg="#0f172a")
            try:
                self.attributes("-alpha", 0.88)
            except tk.TclError:
                pass

        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self._transparent_key, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.panel = Card(self.canvas, padx=18, pady=16)
        self.panel_title = tk.Label(self.panel, text="", font=(FONT, 16, "bold"), fg=TEXT, bg=CARD_BG, justify="left", wraplength=320)
        self.panel_title.pack(anchor="w")

        self.panel_progress = tk.Label(self.panel, text="", font=(FONT, 9), fg=TEXT_SEC, bg=CARD_BG)
        self.panel_progress.pack(anchor="w", pady=(4, 8))

        self.panel_body = tk.Label(self.panel, text="", font=(FONT, 10), fg=TEXT, bg=CARD_BG, justify="left", wraplength=340)
        self.panel_body.pack(anchor="w", fill="x")

        self.button_row = tk.Frame(self.panel, bg=CARD_BG)
        self.button_row.pack(anchor="e", fill="x", pady=(16, 0))

        self.back_button = tk.Button(
            self.button_row,
            text="Back",
            font=(FONT, 10, "bold"),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            activeforeground="#111827",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_back,
        )
        self.back_button.pack(side="left")

        self.skip_button = tk.Button(
            self.button_row,
            text="Skip",
            font=(FONT, 10, "bold"),
            bg="#e5e7eb",
            fg="#111827",
            activebackground="#d1d5db",
            activeforeground="#111827",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_skip,
        )
        self.skip_button.pack(side="left", padx=(8, 0))

        self.next_button = tk.Button(
            self.button_row,
            text="Next",
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._on_next,
        )
        self.next_button.pack(side="right")

        self.bind("<Escape>", lambda e: self._on_skip())
        self.lift()
        self.focus_force()
        self.grab_set()

    def set_bounds(self, width: int, height: int, target_rect: tuple[int, int, int, int] | None) -> None:
        self.canvas.delete("all")
        self.geometry(f"{width}x{height}+{self.app.winfo_rootx()}+{self.app.winfo_rooty()}")
        self.deiconify()
        self.lift()

        if target_rect is None:
            self.canvas.create_rectangle(0, 0, width, height, fill="#0f172a", outline="#0f172a")
            self.canvas.create_window(24, 24, window=self.panel, anchor="nw")
            return

        x1, y1, x2, y2 = target_rect
        pad = 10
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(width, x2 + pad)
        y2 = min(height, y2 + pad)

        if self._supports_transparency:
            shade = "#0f172a"
            self.canvas.create_rectangle(0, 0, width, y1, fill=shade, outline=shade)
            self.canvas.create_rectangle(0, y2, width, height, fill=shade, outline=shade)
            self.canvas.create_rectangle(0, y1, x1, y2, fill=shade, outline=shade)
            self.canvas.create_rectangle(x2, y1, width, y2, fill=shade, outline=shade)
        else:
            self.canvas.create_rectangle(0, 0, width, height, fill="#0f172a", outline="#0f172a")

        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#f59e0b", width=3)

        panel_w = min(400, max(320, width - 48))
        panel_h = 220

        if x2 < width * 0.55:
            panel_x = min(width - panel_w - 24, x2 + 24)
        else:
            panel_x = max(24, x1 - panel_w - 24)

        if y1 < height * 0.55:
            panel_y = min(height - panel_h - 24, y2 + 24)
        else:
            panel_y = max(24, y1 - panel_h - 24)

        self.canvas.create_window(panel_x, panel_y, window=self.panel, anchor="nw")

    def set_content(self, title: str, body: str, progress: str, can_back: bool, is_last: bool) -> None:
        self.panel_title.configure(text=title)
        self.panel_body.configure(text=body)
        self.panel_progress.configure(text=progress)
        self.back_button.configure(state="normal" if can_back else "disabled")
        self.next_button.configure(text="Finish" if is_last else "Next")

    def destroy(self) -> None:
        try:
            super().destroy()
        except Exception:
            pass


class TutorialController:
    """Owns tutorial state, persistence, and overlay rendering."""

    def __init__(self, app: "App", settings: AppSettings) -> None:
        self.app = app
        self.settings = settings
        self.overlay: TutorialOverlay | None = None
        self.steps = self._build_steps()
        self.current_step = 0
        self._active = False

    def start_if_needed(self) -> None:
        if self._active:
            return
        if not self.settings.tutorial_auto_start or self.settings.tutorial_completed:
            return

        start_step = self.settings.tutorial_last_step if 0 <= self.settings.tutorial_last_step < len(self.steps) else 0
        self.start(start_step=start_step)

    def start(self, start_step: int = 0) -> None:
        if not self.steps:
            return

        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

        self._active = True
        self._show_step(max(0, min(start_step, len(self.steps) - 1)))

    def restart(self) -> None:
        self.start(0)

    def finish(self) -> None:
        self.settings.tutorial_completed = True
        self.settings.tutorial_last_step = 0
        save_settings(self.settings)
        self._close_overlay()

    def skip(self) -> None:
        self.finish()

    def next_step(self) -> None:
        if self.current_step >= len(self.steps) - 1:
            self.finish()
            return

        self._show_step(self.current_step + 1)

    def back_step(self) -> None:
        if self.current_step <= 0:
            return

        self._show_step(self.current_step - 1)

    def _close_overlay(self) -> None:
        self._active = False
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    def _show_step(self, step_index: int) -> None:
        step_index = max(0, min(step_index, len(self.steps) - 1))
        self.current_step = step_index
        self.settings.tutorial_last_step = step_index
        save_settings(self.settings)

        step = self.steps[step_index]
        self.app.navigate(step.page_name)
        self.app.update_idletasks()

        if step.prepare is not None:
            step.prepare(self.app)
            self.app.update_idletasks()

        target_widget = self._resolve_target_widget(step, step.target(self.app))
        page = self.app.pages.get(step.page_name)
        if page is not None and target_widget is not None and hasattr(page, "scroll_widget_into_view"):
            try:
                page.scroll_widget_into_view(target_widget)  # type: ignore[call-arg]
            except Exception:
                pass
            self.app.update_idletasks()

        self._ensure_overlay()
        if self.overlay is None:
            return

        target_rect = self._measure_widget(target_widget)
        width = max(1, self.app.winfo_width())
        height = max(1, self.app.winfo_height())
        self.overlay.set_content(
            title=step.title,
            body=step.body,
            progress=f"Step {step_index + 1} of {len(self.steps)}",
            can_back=step_index > 0,
            is_last=step_index == len(self.steps) - 1,
        )
        self.overlay.set_bounds(width, height, target_rect)
        self.overlay.focus_force()

    def _resolve_target_widget(self, step: TutorialStep, widget: tk.Widget | None) -> tk.Widget | None:
        """Return the best visible widget for spotlighting this step."""
        if self._is_spotlightable(widget):
            return widget

        page = self.app.pages.get(step.page_name)
        if self._is_spotlightable(page):
            return page

        nav = self.app.nav_buttons.get(step.page_name)
        if self._is_spotlightable(nav):
            return nav

        return None

    def _is_spotlightable(self, widget: tk.Widget | None) -> bool:
        if widget is None:
            return False

        try:
            widget.update_idletasks()
            return bool(widget.winfo_ismapped()) and widget.winfo_width() > 4 and widget.winfo_height() > 4
        except Exception:
            return False

    def _ensure_overlay(self) -> None:
        if self.overlay is None or not self.overlay.winfo_exists():
            self.overlay = TutorialOverlay(self.app, self.next_step, self.back_step, self.skip)

    def _measure_widget(self, widget: tk.Widget | None) -> tuple[int, int, int, int] | None:
        if widget is None:
            return None

        try:
            widget.update_idletasks()
            if not widget.winfo_ismapped():
                return None

            root_x = self.app.winfo_rootx()
            root_y = self.app.winfo_rooty()
            x1 = widget.winfo_rootx() - root_x
            y1 = widget.winfo_rooty() - root_y
            x2 = x1 + widget.winfo_width()
            y2 = y1 + widget.winfo_height()
            if x2 <= x1 or y2 <= y1:
                return None
            return x1, y1, x2, y2
        except Exception:
            return None

    def _build_steps(self) -> list[TutorialStep]:
        return [
            TutorialStep(
                page_name="Dashboard",
                title="Start Here",
                body=(
                    "This is the dashboard. It summarizes your month, shows recent transactions, and surfaces budget alerts so you can see the big picture at a glance."
                ),
                target=lambda app: app.nav_buttons.get("Dashboard"),
            ),
            TutorialStep(
                page_name="Dashboard",
                title="Read the Summary Cards",
                body=(
                    "The summary cards show income, spending, debt, savings, and your running total. Use them first when you want a quick financial snapshot."
                ),
                target=lambda app: getattr(app.pages["Dashboard"], "card_income", app.pages["Dashboard"].tree),
            ),
            TutorialStep(
                page_name="Add Transaction",
                title="Add New Money Activity",
                body=(
                    "Use Add Transaction when you need to record income, spending, savings transfers, or debt payments. The form changes based on the option you choose."
                ),
                target=lambda app: app.nav_buttons.get("Add Transaction"),
            ),
            TutorialStep(
                page_name="Add Transaction",
                title="Fill Out the Transaction Form",
                body=(
                    "Choose a type, pick or type a category, enter the amount, date, vendor, and description, then submit the record. Special checks appear when the selected category supports savings or debt handling."
                ),
                target=lambda app: app.pages["Add Transaction"].combo_category,
            ),
            TutorialStep(
                page_name="Add Transaction",
                title="Savings Categories Unlock Extra Controls",
                body=(
                    "If you pick a savings category, Budget Planner shows a checkbox that moves the expense into a savings bucket instead of treating it like a normal expense."
                ),
                prepare=self._prepare_add_transaction_savings,
                target=lambda app: app.pages["Add Transaction"].chk_move,
            ),
            TutorialStep(
                page_name="Add Transaction",
                title="Debt Categories Unlock Payment Tracking",
                body=(
                    "If you pick a debt-linked category, the form shows a debt checkbox and a debt selector so the transaction can be applied against the right balance."
                ),
                prepare=self._prepare_add_transaction_debt,
                target=lambda app: app.pages["Add Transaction"].chk_apply_debt,
            ),
            TutorialStep(
                page_name="Debt",
                title="Track Debts",
                body=(
                    "The debt page stores balances, debt types, and payment actions. When you apply a payment, Budget Planner sends you back to Add Transaction with the right debt already selected."
                ),
                target=lambda app: app.nav_buttons.get("Debt"),
            ),
            TutorialStep(
                page_name="Debt",
                title="Add or Update a Debt",
                body=(
                    "Enter a debt name, amount, and type here. The table below shows the current balance, and the buttons let you apply, edit, or remove selected debts."
                ),
                target=lambda app: app.pages["Debt"].tree,
            ),
            TutorialStep(
                page_name="Budget Limits",
                title="Plan Budget Limits",
                body=(
                    "Budget Limits combines advisor guidance, manual sliders, and category management. This is where you shape the plan for each expense category."
                ),
                target=lambda app: app.nav_buttons.get("Budget Limits"),
            ),
            TutorialStep(
                page_name="Budget Limits",
                title="Use the Advisor and Manual Sliders",
                body=(
                    "The advisor helps generate suggested limits, while the sliders let you fine-tune each expense category by percentage. Use both together when building a realistic monthly plan."
                ),
                target=lambda app: app.pages["Budget Limits"].slider_rows_frame,
            ),
            TutorialStep(
                page_name="Budget Limits",
                title="Manage Categories",
                body=(
                    "The category manager is where you add, rename, archive, reactivate, or import categories. It also keeps the default category list and suggestion list organized for future use."
                ),
                target=lambda app: app.pages["Budget Limits"].category_select_combo,
            ),
            TutorialStep(
                page_name="History",
                title="Review Every Transaction",
                body=(
                    "History is the ledger view. It shows every transaction, lets you filter the list, edit entries, print reports, and remove rows when needed."
                ),
                target=lambda app: app.nav_buttons.get("History"),
            ),
            TutorialStep(
                page_name="History",
                title="Filter the Ledger",
                body=(
                    "The filter row lets you narrow results by category, vendor, type, month, and year. Use these filters before you print or edit a report."
                ),
                target=lambda app: app.pages["History"].category_dropdown.button,
            ),
            TutorialStep(
                page_name="Charts",
                title="See the Charts",
                body=(
                    "Charts turn your spending history into visuals. They make it easier to spot category concentration, vendor concentration, and monthly trends over time."
                ),
                target=lambda app: app.nav_buttons.get("Charts"),
            ),
            TutorialStep(
                page_name="Charts",
                title="Read the Spending Charts",
                body=(
                    "Use the pie charts to understand where money is going this month, and the bar chart to compare income versus spending across the last six months."
                ),
                target=lambda app: app.pages["Charts"].canvas_pie_cat.get_tk_widget(),
            ),
            TutorialStep(
                page_name="Savings",
                title="Watch Savings Grow",
                body=(
                    "Savings shows the forecast, growth chart, and savings transaction history. It helps you see whether your savings behavior is on track for the goals you care about."
                ),
                target=lambda app: app.nav_buttons.get("Savings"),
            ),
            TutorialStep(
                page_name="Savings",
                title="Inspect the Forecast and History",
                body=(
                    "The forecast explains what your savings pace means over time, while the table below keeps a log of the actual savings transactions that created that trend."
                ),
                target=lambda app: app.pages["Savings"].forecast_text,
            ),
            TutorialStep(
                page_name="Settings",
                title="Tune Updates and Tutorial Behavior",
                body=(
                    "Settings holds update preferences and the tutorial controls. You can turn startup tutorial replay on or off, restart the tour on demand, and reset completion when you want the app to show it again."
                ),
                target=lambda app: app.nav_buttons.get("Settings"),
            ),
            TutorialStep(
                page_name="Settings",
                title="Replay the Tutorial Any Time",
                body=(
                    "Use Start Tutorial to replay the walkthrough immediately. If you want the app to show the tour again on a future launch, reset completion after turning on startup playback."
                ),
                target=lambda app: app.pages["Settings"].btn_start_tutorial,
            ),
            TutorialStep(
                page_name="Dashboard",
                title="You’re Ready",
                body=(
                    "You now know where to record transactions, review history, manage budgets, inspect charts, track savings, and adjust settings. Start with Dashboard, then move into Add Transaction and Budget Limits as your day-to-day workflow."
                ),
                target=lambda app: app.nav_buttons.get("Dashboard"),
            ),
        ]

    def _prepare_add_transaction_savings(self, app: "App") -> None:
        page = app.pages["Add Transaction"]
        expense_names = list(app.category_repo.names("expense"))

        page.var_type.set("expense")
        page._update_categories()

        savings_category = next((name for name in expense_names if app.category_repo.is_savings_category(name)), None)
        if savings_category:
            page._set_category_choices("expense", savings_category)
            page.var_move.set(True)
            page.var_spend.set(False)
            page.var_apply_debt.set(False)
            page._update_savings_ui()
            page._update_debt_ui()
            page._refresh_debt_dropdown()
            return

        page._update_savings_ui()
        page._update_debt_ui()
        page._refresh_debt_dropdown()

    def _prepare_add_transaction_debt(self, app: "App") -> None:
        page = app.pages["Add Transaction"]
        expense_names = list(app.category_repo.names("expense"))

        page.var_type.set("expense")
        page._update_categories()

        debt_category = next((name for name in expense_names if app.category_repo.debt_type_for_category(name)), None)
        if debt_category:
            page._set_category_choices("expense", debt_category)
            page.var_move.set(False)
            page.var_spend.set(False)
            page.var_apply_debt.set(True)
            page._update_savings_ui()
            page._update_debt_ui()
            page._refresh_debt_dropdown()
            return

        page._update_savings_ui()
        page._update_debt_ui()
        page._refresh_debt_dropdown()