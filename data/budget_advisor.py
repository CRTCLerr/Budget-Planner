"""
Budget Advisor service.

A more realistic financial planner that:
- Uses income and history
- Applies a needs/wants/financial (50/30/20-inspired) structure
- Adjusts behavior by mode: balanced, savings, debt, event
- Produces human-readable insights to explain its choices
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Literal, Any, Tuple

from .categories import CategoryRepository
from .transactions import TransactionRepository
from .debt import DebtRepository
from .savings import SavingsService
from .budgets import BudgetRepository


Mode = Literal["balanced", "savings", "debt", "event"]
HistoryMode = Literal["3m", "6m", "12m", "seasonal", "all"]

# Target shares of income (50/30/20 inspired)
TARGET_NEEDS_SHARE = 0.50
TARGET_WANTS_SHARE = 0.30
TARGET_FINANCIAL_SHARE = 0.20

@dataclass
class EventGoal:
    name: str
    target_amount: float
    target_date: date


@dataclass
class BudgetRecommendation:
    mode: Mode
    month_income: float
    month_expenses: float
    category_budgets: Dict[str, float]
    savings_target: float
    debt_target: float
    event_goal: Optional[EventGoal]
    insights: List[str]


class BudgetAdvisorService:
    def __init__(
        self,
        tx_repo: TransactionRepository,
        debt_repo: DebtRepository,
        savings_service: SavingsService,
        budget_repo: BudgetRepository,
        category_repo: CategoryRepository,
        mode: Mode = "balanced",
        history_mode: HistoryMode = "6m",
        event_goal: Optional[EventGoal] = None,
    ) -> None:
        self.tx_repo = tx_repo
        self.debt_repo = debt_repo
        self.savings_service = savings_service
        self.budget_repo = budget_repo
        self.category_repo = category_repo
        self.mode = mode
        self.history_mode = history_mode
        self.event_goal = event_goal

    def _expense_categories(self) -> List[str]:
        return self.category_repo.names("expense")

    def _category_group(self, category: str) -> str:
        found = self.category_repo.get(category, "expense")
        return found.advisor_group if found is not None else "wants"

    def _categories_for_group(self, advisor_group: str) -> set[str]:
        return set(self.category_repo.expense_names_by_group(advisor_group))

    def _weight_for_category(self, category: str) -> float:
        record = self.category_repo.get(category, "expense")
        if record is None:
            return 0.05

        if record.is_savings:
            return 0.12
        if record.debt_type == "utility":
            return 0.11
        if record.debt_type in ("credit", "loan"):
            return 0.09
        if record.advisor_group == "needs":
            return 0.09
        if record.advisor_group == "financial":
            return 0.07
        return 0.05

    def _seasonal_multiplier(self, category: str, today: Optional[date] = None) -> float:
        """Apply broad seasonal effects from category metadata, not category names."""
        if today is None:
            today = datetime.today().date()

        month = today.month
        record = self.category_repo.get(category, "expense")
        if record is None:
            return 1.0

        if record.debt_type == "utility":
            if month in (11, 12, 1, 2, 3):
                return 1.20
            if month in (6, 7, 8):
                return 1.08

        if record.advisor_group == "wants" and month in (11, 12):
            return 1.10

        return 1.0

    def _expense_category_records(self):
        return self.category_repo.expense_categories()

    def _savings_category_name(self) -> Optional[str]:
        for category in self._expense_category_records():
            if category.is_savings:
                return category.name
        return None

    def _debt_budget_total(self, category_budgets: Dict[str, float]) -> float:
        total = 0.0
        for category in self._expense_category_records():
            if category.debt_type in ("credit", "loan"):
                total += category_budgets.get(category.name, 0.0)
        return total

    def _flex_wants_categories(self) -> List[str]:
        return [category.name for category in self._expense_category_records() if category.advisor_group == "wants"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_history_mode(self, mode: HistoryMode) -> None:
        self.history_mode = mode

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode

    def set_event_goal(self, goal: Optional[EventGoal]) -> None:
        self.event_goal = goal

    def generate_recommendation(self) -> BudgetRecommendation:
        data = self._analyze_spending()

        if self.mode == "savings":
            return self._strategy_savings(data)
        elif self.mode == "debt":
            return self._strategy_debt(data)
        elif self.mode == "event":
            return self._strategy_event(data, self.event_goal)
        else:
            return self._strategy_balanced(data)

    def apply_to_budgets(self, rec: BudgetRecommendation) -> None:
        """
        Apply recommended limits to the budgets table.

        Ensures no zero/negative limits (CHECK constraint safety).
        """
        num_cats = max(len(rec.category_budgets), 1)
        baseline = rec.month_income / num_cats if rec.month_income > 0 else 50.0

        for cat, limit in rec.category_budgets.items():
            safe_limit = float(limit) if limit and limit > 0 else baseline
            self.budget_repo.set_budget(cat, safe_limit)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _legacy_duplicate_analyze_spending(self) -> Dict[str, Any]:
        """
        Look back over history to understand:
        - Last month's income
        - Average monthly spend per category (last 3–6 months)
        - Total remaining debt
        """
        today = datetime.today().date()

        last_month_date = (today.replace(day=1) - timedelta(days=1))
        last_month = last_month_date.month
        last_year = last_month_date.year

        six_months_ago = today - timedelta(days=180)
        three_months_ago = today - timedelta(days=90)

        all_txs = self.tx_repo.history()

        income_last_month = 0.0
        expense_categories = self._expense_categories()
        needs_categories = self._categories_for_group("needs")
        history: Dict[str, List[float]] = {cat: [] for cat in expense_categories}

        for t in all_txs:
            try:
                t_date = datetime.strptime(t.date, "%Y-%m-%d").date()
            except Exception:
                continue

            # Income for last month
            if getattr(t, "type", "") == "income" and t_date.month == last_month and t_date.year == last_year:
                income_last_month += t.amount

            # Only consider expenses / savings_spend for category history
            if getattr(t, "type", "") not in ("expense", "savings_spend"):
                continue

            if t.category in history:
                # Needs → 6 months
                if t.category in needs_categories and t_date >= six_months_ago:
                    history[t.category].append(t.amount)
                # Wants / Financial → 3 months
                elif t_date >= three_months_ago:
                    history[t.category].append(t.amount)

        avg_history = {
            cat: (sum(vals) / len(vals)) if vals else 0.0
            for cat, vals in history.items()
        }

        # Approximate total remaining debt from DebtRepository
        total_debt_remaining = 0.0
        try:
            for d in self.debt_repo.all():
                total_debt_remaining += getattr(d, "remaining", 0.0)
        except Exception:
            total_debt_remaining = 0.0

        return {
            "income_last_month": income_last_month,
            "avg_history": avg_history,
            "total_debt_remaining": total_debt_remaining,
        }

    # ------------------------------------------------------------------
    # Core helpers: savings forecasting, allocation, carry-over
    # ------------------------------------------------------------------

    def _legacy_duplicate_forecast_savings(self, monthly_savings: float, avg_history: Dict[str, float]) -> Dict[str, str]:
        """
        Forecast savings milestones based on current savings and monthly contributions.
        Returns human-readable milestone estimates.
        """
        try:
            current_savings = self.savings_service.total_savings()
        except Exception:
            current_savings = 0.0

        # Monthly expenses baseline (use all categories' averages)
        monthly_expenses = sum(avg_history.values())
        if monthly_expenses <= 0:
            monthly_expenses = 2000  # fallback baseline

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

            # Compute target date
            year = today.year + (today.month + months_needed - 1) // 12
            month = (today.month + months_needed - 1) % 12 + 1
            target_date = date(year, month, 1)

            results[label] = f"Reached by {target_date.strftime('%Y-%m')}"

        return results

    def _legacy_duplicate_base_allocation(
        self,
        income: float,
        avg_history: Dict[str, float],
        needs_share: float,
        wants_share: float,
        financial_share: float,
    ) -> Dict[str, float]:
        """
        FINAL VERSION — Pure History + Pure Weight Allocation
        -----------------------------------------------------
        Rules:
        - Categories WITH history use ONLY their monthly average.
        - Categories WITHOUT history use ONLY redistributed weights.
        - Weights from history categories are removed from the pool.
        - Remaining weights are normalized.
        - NO seasonal multipliers.
        """

        if income <= 0:
            return {cat: 0.0 for cat in self._expense_categories()}

        # Income buckets
        needs_income = income * needs_share
        wants_income = income * wants_share
        financial_income = income * financial_share
        all_expense_categories = self._expense_categories()
        needs_categories = self._categories_for_group("needs")
        wants_categories = self._categories_for_group("wants")
        financial_categories = self._categories_for_group("financial")

        budgets: Dict[str, float] = {}

        def allocate_bucket(cats: set[str], bucket_income: float) -> None:
            # 1. Split categories into history vs no-history
            hist_cats = {c for c in cats if avg_history.get(c, 0.0) > 0}
            no_hist_cats = cats - hist_cats

            # 2. Allocate history categories directly
            hist_total = 0.0
            for c in hist_cats:
                amt = avg_history.get(c, 0.0)
                budgets[c] = amt
                hist_total += amt

            # 3. Remaining budget for non-history categories
            remaining = max(bucket_income - hist_total, 0.0)

            if not no_hist_cats:
                return

            # 4. Build weight pool ONLY from non-history categories
            weight_pool = {c: self._weight_for_category(c) for c in no_hist_cats}
            total_weight = sum(weight_pool.values())

            # If no weights exist, split evenly
            if total_weight <= 0:
                per_cat = remaining / len(no_hist_cats)
                for c in no_hist_cats:
                    budgets[c] = per_cat
                return

            # 5. Allocate using normalized weights
            for c in no_hist_cats:
                w = weight_pool[c] / total_weight
                budgets[c] = remaining * w

        # Allocate each bucket
        allocate_bucket(needs_categories, needs_income)
        allocate_bucket(wants_categories, wants_income)
        allocate_bucket(financial_categories, financial_income)

        # Ensure all categories exist
        for c in all_expense_categories:
            budgets.setdefault(c, 0.0)

        return {c: round(v, 2) for c, v in budgets.items()}

    def _legacy_duplicate_apply_carryover(
        self,
        income: float,
        category_budgets: Dict[str, float],
        savings_target: float,
    ) -> float:
        """
        Apply carry-over logic:
        - Any leftover income after category budgets is mostly pushed to Savings,
          with a small portion to Shopping and Other.
        Returns updated savings_target.
        """
        total_spend = sum(category_budgets.values())
        leftover = max(income - total_spend, 0.0)
        if leftover <= 0:
            return savings_target

        savings_extra = leftover * 0.80
        flex_extra = leftover * 0.20

        # Push most to savings
        savings_target += savings_extra

        flex_targets = self._flex_wants_categories()[:2]
        if flex_targets:
            split = flex_extra / len(flex_targets)
            for category_name in flex_targets:
                if category_name in category_budgets:
                    category_budgets[category_name] += split

        return savings_target

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _legacy_duplicate_strategy_balanced(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=TARGET_NEEDS_SHARE,
            wants_share=TARGET_WANTS_SHARE,
            financial_share=TARGET_FINANCIAL_SHARE,
        )

        total_spend = sum(category_budgets.values())
        leftover = max(income - total_spend, 0.0)

        # Split leftover between savings and debt
        savings_extra = leftover * 0.5
        debt_extra = leftover * 0.5

        savings_name = self._savings_category_name()
        savings_target = round(category_budgets.get(savings_name, 0.0) + savings_extra, 2) if savings_name else round(savings_extra, 2)

        # Apply carry-over behavior (push extra to savings + flexible)
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = round(self._debt_budget_total(category_budgets) + debt_extra, 2)

        forecast = self._forecast_savings(
            monthly_savings=savings_target,
            avg_history=avg_history,
        )

        insights: List[str] = []
        insights.append(
            "Balanced mode: using a 50/30/20-style structure (needs/wants/financial) "
            "blended with your recent spending patterns and default category priorities."
        )
        if total_debt > 0:
            insights.append(
                f"Total remaining debt detected: about ${total_debt:,.0f}. "
                "Part of your leftover income is directed toward extra debt payments."
            )
        else:
            insights.append(
                "No active debts detected; more flexibility is available for savings and lifestyle."
            )

        for label, msg in forecast.items():
            insights.append(f"{label}: {msg}")

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="balanced",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=debt_target,
            event_goal=None,
            insights=insights,
        )

    def _legacy_duplicate_strategy_savings(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        # Tilt more toward financial (savings) by shrinking wants
        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=0.50,
            wants_share=0.20,
            financial_share=0.30,
        )

        total_spend = sum(category_budgets.values())
        leftover = max(income - total_spend, 0.0)

        savings_extra = leftover * 0.7
        debt_extra = leftover * 0.3

        savings_name = self._savings_category_name()
        savings_target = round(category_budgets.get(savings_name, 0.0) + savings_extra, 2) if savings_name else round(savings_extra, 2)

        # Apply carry-over behavior
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = round(self._debt_budget_total(category_budgets) + debt_extra, 2)

        forecast = self._forecast_savings(
            monthly_savings=savings_target,
            avg_history=avg_history,
        )

        insights: List[str] = []
        insights.append(
            "Savings mode: lifestyle spending is trimmed so more of your income can be directed into savings."
        )
        if total_debt > 0:
            insights.append(
                "Debt is still funded, but savings is prioritized. "
                "If your debt feels heavy, consider switching to Debt mode for a while."
            )

        for label, msg in forecast.items():
            insights.append(f"{label}: {msg}")

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="savings",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=debt_target,
            event_goal=None,
            insights=insights,
        )

    def _legacy_duplicate_strategy_debt(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        # Tilt heavily toward financial (debt payoff) by cutting wants
        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=0.55,
            wants_share=0.15,
            financial_share=0.30,
        )

        total_spend = sum(category_budgets.values())
        leftover = max(income - total_spend, 0.0)

        # In debt mode, leftover goes mostly to debt
        savings_extra = leftover * 0.2
        debt_extra = leftover * 0.8

        savings_name = self._savings_category_name()
        savings_target = round(category_budgets.get(savings_name, 0.0) + savings_extra, 2) if savings_name else round(savings_extra, 2)

        # Carry-over still pushes some extra into savings + flexible
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = round(self._debt_budget_total(category_budgets) + debt_extra, 2)

        insights: List[str] = []
        insights.append(
            "Debt mode: wants are intentionally constrained so you can push more money toward debt payoff."
        )
        if total_debt > 0:
            insights.append(
                f"With about ${total_debt:,.0f} in remaining debt, this plan is designed to accelerate progress "
                "without starving essentials."
            )
        else:
            insights.append(
                "No active debts detected; Debt mode may not be necessary right now."
            )

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="debt",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=debt_target,
            event_goal=None,
            insights=insights,
        )

    def _legacy_duplicate_strategy_event(self, data: Dict[str, Any], goal: Optional[EventGoal]) -> BudgetRecommendation:
        """
        Event mode: start from balanced, then carve out a dedicated event line
        by trimming wants and a bit of savings, without touching needs.
        """
        base_rec = self._strategy_balanced(data)

        if not goal:
            base_rec.insights.append(
                "Event mode selected, but no event goal was provided. "
                "Set an event name, amount, and date to see a dedicated event line."
            )
            return base_rec

        today = datetime.today().date()
        months_left = max(
            1,
            (goal.target_date.year - today.year) * 12
            + (goal.target_date.month - today.month),
        )

        per_month = goal.target_amount / months_left
        event_cat = f"Event: {goal.name}"

        # Create or update event category
        base_rec.category_budgets[event_cat] = round(per_month, 2)

        # Fund event primarily from wants + some savings
        remaining = per_month
        trim_order = self._flex_wants_categories()

        for cat in trim_order:
            if remaining <= 0:
                break
            if cat not in base_rec.category_budgets:
                continue
            current = base_rec.category_budgets[cat]
            if current <= 0:
                continue
            trim = min(current * 0.5, remaining)  # trim up to 50% of that category
            base_rec.category_budgets[cat] = max(current - trim, 0.0)
            remaining -= trim

        # If still not fully funded, trim a bit from Savings
        savings_name = self._savings_category_name()
        if remaining > 0 and savings_name and savings_name in base_rec.category_budgets:
            current = base_rec.category_budgets[savings_name]
            trim = min(current * 0.3, remaining)  # up to 30% of savings allocation
            base_rec.category_budgets[savings_name] = max(current - trim, 0.0)
            remaining -= trim

        base_rec.insights.append(
            f"Event '{goal.name}': to reach ${goal.target_amount:,.0f} by "
            f"{goal.target_date.strftime('%Y-%m')}, you need about ${per_month:,.0f}/month."
        )
        base_rec.insights.append(
            "This event line is funded primarily by trimming Dining Out, Entertainment, Shopping, and similar wants, "
            "with a small adjustment to Savings if needed."
        )

        base_rec.event_goal = goal
        base_rec.month_expenses = sum(base_rec.category_budgets.values())

        return base_rec

    # ------------------------------------------------------------------
    # Analysis: monthly history, income, debt
    # ------------------------------------------------------------------

    def _history_window_cutoff(self, today: date) -> Optional[date]:
        """Return the earliest date to include based on history_mode."""
        if self.history_mode == "3m":
            return today - timedelta(days=92)
        if self.history_mode == "6m":
            return today - timedelta(days=185)
        if self.history_mode == "12m":
            return today - timedelta(days=365)
        if self.history_mode == "seasonal":
            # For now, treat as last 12 months; seasonal multipliers handle seasonality.
            return today - timedelta(days=365)
        if self.history_mode == "all":
            return None
        return None

    def _compute_monthly_category_averages(
        self,
        today: date,
    ) -> Dict[str, float]:
        """
        Compute monthly averages per category based on monthly totals,
        not per-transaction averages.

        For each category:
        - Group expenses/savings_spend by (year, month)
        - Sum within each month
        - Average those monthly totals across the selected window
        """
        cutoff = self._history_window_cutoff(today)
        all_txs = self.tx_repo.history()

        # category -> {(year, month): total_for_that_month}
        expense_categories = self._expense_categories()
        monthly_totals: Dict[str, Dict[Tuple[int, int], float]] = {cat: {} for cat in expense_categories}

        for t in all_txs:
            try:
                t_date = datetime.strptime(t.date, "%Y-%m-%d").date()
            except Exception:
                continue

            if cutoff is not None and t_date < cutoff:
                continue

            if getattr(t, "type", "") not in ("expense", "savings_spend"):
                continue

            if t.category not in monthly_totals:
                continue

            ym = (t_date.year, t_date.month)
            bucket = monthly_totals[t.category]
            bucket[ym] = bucket.get(ym, 0.0) + t.amount

        avg_history: Dict[str, float] = {}
        for cat, months in monthly_totals.items():
            if not months:
                avg_history[cat] = 0.0
                continue
            total = sum(months.values())
            count = len(months)
            avg_history[cat] = total / count

        return avg_history

    def _analyze_spending(self) -> Dict[str, Any]:
        """
        Look back over history to understand:
        - Last month's income
        - Average monthly spend per category (based on monthly totals)
        - Total remaining debt
        """
        today = datetime.today().date()

        last_month_date = (today.replace(day=1) - timedelta(days=1))
        last_month = last_month_date.month
        last_year = last_month_date.year

        all_txs = self.tx_repo.history()

        income_last_month = 0.0
        for t in all_txs:
            try:
                t_date = datetime.strptime(t.date, "%Y-%m-%d").date()
            except Exception:
                continue

            if getattr(t, "type", "") == "income" and t_date.month == last_month and t_date.year == last_year:
                income_last_month += t.amount

        avg_history = self._compute_monthly_category_averages(today)

        # Approximate total remaining debt from DebtRepository
        total_debt_remaining = 0.0
        try:
            for d in self.debt_repo.all():
                total_debt_remaining += getattr(d, "remaining", 0.0)
        except Exception:
            total_debt_remaining = 0.0

        return {
            "income_last_month": income_last_month,
            "avg_history": avg_history,
            "total_debt_remaining": total_debt_remaining,
        }

    # ------------------------------------------------------------------
    # Core helpers: savings forecasting, allocation, carry-over
    # ------------------------------------------------------------------

    def _forecast_savings(self, monthly_savings: float, avg_history: Dict[str, float]) -> Dict[str, str]:
        """
        Forecast savings milestones based on current savings and monthly contributions.
        Returns human-readable milestone estimates.
        """
        try:
            current_savings = self.savings_service.total_savings()
        except Exception:
            current_savings = 0.0

        # Monthly expenses baseline (use all categories' averages)
        monthly_expenses = sum(avg_history.values())
        if monthly_expenses <= 0:
            monthly_expenses = 2000  # fallback baseline

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

            # Compute target date
            year = today.year + (today.month + months_needed - 1) // 12
            month = (today.month + months_needed - 1) % 12 + 1
            target_date = date(year, month, 1)

            results[label] = f"Reached by {target_date.strftime('%Y-%m')}"

        return results

    def _base_allocation(
        self,
        income: float,
        avg_history: Dict[str, float],
        needs_share: float,
        wants_share: float,
        financial_share: float,
    ) -> Dict[str, float]:
        """
        Allocate income across categories using:
        - Needs/Wants/Financial target shares
        - Monthly historical averages as anchors
        - Default weights when history is missing
        - Seasonal multipliers
        - History-first: if a category has history, use it directly;
          weights fill the remaining bucket.
        """
        if income <= 0:
            return {cat: 0.0 for cat in self._expense_categories()}

        today = datetime.today().date()

        needs_income = income * needs_share
        wants_income = income * wants_share
        financial_income = income * financial_share
        all_expense_categories = self._expense_categories()
        needs_categories = self._categories_for_group("needs")
        wants_categories = self._categories_for_group("wants")
        financial_categories = self._categories_for_group("financial")

        budgets: Dict[str, float] = {}

        def allocate_bucket(cats: set[str], bucket_income: float) -> None:
            if bucket_income <= 0 or not cats:
                for c in cats:
                    budgets[c] = 0.0
                return

            # Split into history and no-history categories
            hist_cats = [c for c in cats if avg_history.get(c, 0.0) > 0]
            no_hist_cats = [c for c in cats if avg_history.get(c, 0.0) <= 0]

            # 1) Assign history categories their monthly averages
            hist_total = sum(avg_history.get(c, 0.0) for c in hist_cats)

            if hist_total >= bucket_income and hist_total > 0:
                # Scale history down proportionally to fit the bucket
                for c in hist_cats:
                    share = avg_history.get(c, 0.0) / hist_total
                    base = bucket_income * share
                    mult = self._seasonal_multiplier(c, today)
                    budgets[c] = base * mult
                # No room for no-history categories
                for c in no_hist_cats:
                    budgets[c] = 0.0
                return

            # Otherwise, give history categories their full monthly averages
            remaining = bucket_income
            for c in hist_cats:
                base = avg_history.get(c, 0.0)
                mult = self._seasonal_multiplier(c, today)
                amt = base * mult
                budgets[c] = amt
                remaining -= amt

            remaining = max(0.0, remaining)

            # 2) Use weights to distribute remaining among no-history categories
            if not no_hist_cats or remaining <= 0:
                for c in no_hist_cats:
                    budgets.setdefault(c, 0.0)
                return

            total_weight = sum(self._weight_for_category(c) for c in no_hist_cats)
            if total_weight <= 0:
                per_cat = remaining / len(no_hist_cats)
                for c in no_hist_cats:
                    mult = self._seasonal_multiplier(c, today)
                    budgets[c] = per_cat * mult
                return

            for c in no_hist_cats:
                w = self._weight_for_category(c)
                share = w / total_weight if total_weight > 0 else 0.0
                base = remaining * share
                mult = self._seasonal_multiplier(c, today)
                budgets[c] = base * mult

        allocate_bucket(needs_categories, needs_income)
        allocate_bucket(wants_categories, wants_income)
        allocate_bucket(financial_categories, financial_income)

        # Ensure all categories exist in dict
        for c in all_expense_categories:
            budgets.setdefault(c, 0.0)

        return {c: round(v, 2) for c, v in budgets.items()}

    def _apply_carryover(
        self,
        income: float,
        category_budgets: Dict[str, float],
        savings_target: float,
    ) -> float:
        """
        Apply carry-over logic:
        - Any leftover income after category budgets is mostly pushed to Savings,
          with a small portion to Shopping and Other.
        Returns updated savings_target.
        """
        total_spend = sum(category_budgets.values())
        leftover = max(income - total_spend, 0.0)
        if leftover <= 0:
            return savings_target

        savings_extra = leftover * 0.80
        flex_extra = leftover * 0.20

        # Push most to savings
        savings_target += savings_extra

        flex_targets = self._flex_wants_categories()[:2]
        if flex_targets:
            split = flex_extra / len(flex_targets)
            for category_name in flex_targets:
                if category_name in category_budgets:
                    category_budgets[category_name] += split

        return savings_target

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _strategy_balanced(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=TARGET_NEEDS_SHARE,
            wants_share=TARGET_WANTS_SHARE,
            financial_share=TARGET_FINANCIAL_SHARE,
        )

        total_spend = sum(category_budgets.values())

        savings_name = self._savings_category_name()
        savings_target = category_budgets.get(savings_name, 0.0) if savings_name else 0.0

        # Apply carry-over behavior (push extra to savings + flexible)
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = self._debt_budget_total(category_budgets)

        forecast = self._forecast_savings(
            monthly_savings=savings_target,
            avg_history=avg_history,
        )

        insights: List[str] = []
        insights.append(
            "Balanced mode: using a 50/30/20-style structure (needs/wants/financial) "
            "anchored to your average monthly spending per category, with weights filling gaps."
        )
        if total_debt > 0:
            insights.append(
                f"Total remaining debt detected: about ${total_debt:,.0f}. "
                "Part of your leftover income is directed toward extra debt payments."
            )
        else:
            insights.append(
                "No active debts detected; more flexibility is available for savings and lifestyle."
            )

        for label, msg in forecast.items():
            insights.append(f"{label}: {msg}")

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="balanced",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=round(debt_target, 2),
            event_goal=None,
            insights=insights,
        )

    def _strategy_savings(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        # Tilt more toward financial (savings) by shrinking wants
        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=0.50,
            wants_share=0.20,
            financial_share=0.30,
        )

        total_spend = sum(category_budgets.values())

        savings_name = self._savings_category_name()
        savings_target = category_budgets.get(savings_name, 0.0) if savings_name else 0.0

        # Apply carry-over behavior
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = self._debt_budget_total(category_budgets)

        forecast = self._forecast_savings(
            monthly_savings=savings_target,
            avg_history=avg_history,
        )

        insights: List[str] = []
        insights.append(
            "Savings mode: lifestyle spending is trimmed so more of your income can be directed into savings."
        )
        if total_debt > 0:
            insights.append(
                "Debt is still funded, but savings is prioritized. "
                "If your debt feels heavy, consider switching to Debt mode for a while."
            )

        for label, msg in forecast.items():
            insights.append(f"{label}: {msg}")

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="savings",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=round(debt_target, 2),
            event_goal=None,
            insights=insights,
        )

    def _strategy_debt(self, data: Dict[str, Any]) -> BudgetRecommendation:
        income = data["income_last_month"]
        avg_history = data["avg_history"]
        total_debt = data["total_debt_remaining"]

        # Tilt heavily toward financial (debt payoff) by cutting wants
        category_budgets = self._base_allocation(
            income=income,
            avg_history=avg_history,
            needs_share=0.55,
            wants_share=0.15,
            financial_share=0.30,
        )

        total_spend = sum(category_budgets.values())

        savings_name = self._savings_category_name()
        savings_target = category_budgets.get(savings_name, 0.0) if savings_name else 0.0

        # Carry-over still pushes some extra into savings + flexible
        savings_target = self._apply_carryover(income, category_budgets, savings_target)

        debt_target = self._debt_budget_total(category_budgets)

        insights: List[str] = []
        insights.append(
            "Debt mode: wants are intentionally constrained so you can push more money toward debt payoff."
        )
        if total_debt > 0:
            insights.append(
                f"With about ${total_debt:,.0f} in remaining debt, this plan is designed to accelerate progress "
                "without starving essentials."
            )
        else:
            insights.append(
                "No active debts detected; Debt mode may not be necessary right now."
            )

        total_spend = sum(category_budgets.values())

        return BudgetRecommendation(
            mode="debt",
            month_income=income,
            month_expenses=total_spend,
            category_budgets=category_budgets,
            savings_target=round(savings_target, 2),
            debt_target=round(debt_target, 2),
            event_goal=None,
            insights=insights,
        )

    def _strategy_event(self, data: Dict[str, Any], goal: Optional[EventGoal]) -> BudgetRecommendation:
        """
        Event mode: start from balanced, then carve out a dedicated event line
        by trimming wants and a bit of savings, without touching needs.
        """
        base_rec = self._strategy_balanced(data)

        if not goal:
            base_rec.insights.append(
                "Event mode selected, but no event goal was provided. "
                "Set an event name, amount, and date to see a dedicated event line."
            )
            return base_rec

        today = datetime.today().date()
        months_left = max(
            1,
            (goal.target_date.year - today.year) * 12
            + (goal.target_date.month - today.month),
        )

        per_month = goal.target_amount / months_left
        event_cat = f"Event: {goal.name}"

        # Create or update event category
        base_rec.category_budgets[event_cat] = round(per_month, 2)

        # Fund event primarily from wants + some savings
        remaining = per_month
        trim_order = self._flex_wants_categories()

        for cat in trim_order:
            if remaining <= 0:
                break
            if cat not in base_rec.category_budgets:
                continue
            current = base_rec.category_budgets[cat]
            if current <= 0:
                continue
            trim = min(current * 0.5, remaining)  # trim up to 50% of that category
            base_rec.category_budgets[cat] = max(current - trim, 0.0)
            remaining -= trim

        # If still not fully funded, trim a bit from Savings
        savings_name = self._savings_category_name()
        if remaining > 0 and savings_name and savings_name in base_rec.category_budgets:
            current = base_rec.category_budgets[savings_name]
            trim = min(current * 0.3, remaining)  # up to 30% of savings allocation
            base_rec.category_budgets[savings_name] = max(current - trim, 0.0)
            remaining -= trim

        base_rec.insights.append(
            f"Event '{goal.name}': to reach ${goal.target_amount:,.0f} by "
            f"{goal.target_date.strftime('%Y-%m')}, you need about ${per_month:,.0f}/month."
        )
        base_rec.insights.append(
            "This event line is funded primarily by trimming Dining Out, Entertainment, Shopping, and similar wants, "
            "with a small adjustment to Savings if needed."
        )

        base_rec.event_goal = goal
        base_rec.month_expenses = sum(base_rec.category_budgets.values())

        return base_rec
