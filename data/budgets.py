"""
Budgets data access layer.

Handles setting, removing, listing budgets and computing alerts
based on monthly spending.

Now includes backward‑compatible normalization for legacy
"Debt Payment" category, mapping it to "Credit Card Payment".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .database import Database
from .transactions import TransactionRepository


@dataclass
class Budget:
    """Domain model for a budget limit per category."""
    id: int
    category: str
    limit_amount: float


class BudgetRepository:
    """Repository for interacting with the budgets table."""

    LEGACY_CATEGORY_MAP = {
        "Debt Payment": "Credit Card Payment",
    }

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Internal normalization
    # ------------------------------------------------------------------

    def _normalize_category(self, category: str) -> str:
        """
        Normalize category names for backward compatibility.

        - Legacy: "Debt Payment" → "Credit Card Payment"
        """
        return self.LEGACY_CATEGORY_MAP.get(category, category)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def set_budget(self, category: str, amount: float) -> None:
        """
        Insert or update a budget for a category.
        """
        category = self._normalize_category(category)

        self.db.conn.execute(
            """
            INSERT INTO budgets (category, limit_amount)
            VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET limit_amount = excluded.limit_amount;
            """,
            (category, amount),
        )
        self.db.conn.commit()

    def remove_budget(self, category: str) -> None:
        """Remove a budget for a category."""
        category = self._normalize_category(category)

        self.db.conn.execute(
            "DELETE FROM budgets WHERE category = ?;",
            (category,),
        )
        self.db.conn.commit()

    def all(self) -> List[Budget]:
        """Return all budgets."""
        cur = self.db.conn.execute(
            "SELECT * FROM budgets ORDER BY category ASC;"
        )
        return [
            Budget(
                id=row["id"],
                category=row["category"],
                limit_amount=float(row["limit_amount"]),
            )
            for row in cur.fetchall()
        ]

    def _is_active_category_or_unknown(self, category: str) -> bool:
        """Treat known inactive categories as hidden from active budget workflows."""
        row = self.db.conn.execute(
            "SELECT active FROM categories WHERE kind = 'expense' AND LOWER(name) = LOWER(?) ORDER BY id ASC LIMIT 1;",
            (category,),
        ).fetchone()
        if row is None:
            return True
        return bool(row["active"])

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def alerts(
        self,
        tx_repo: TransactionRepository,
        month: int,
        year: int,
    ) -> List[Tuple[str, float, float, float, str]]:
        """
        Compute budget alerts for a given month/year.

        Returns a list of tuples:
        (category, spent, limit, pct, level)
        where level is "over", "warn", or "ok".
        """
        summary = tx_repo.month_summary(month, year)
        by_cat: Dict[str, float] = summary["by_cat"]
        alerts: List[Tuple[str, float, float, float, str]] = []

        for b in self.all():
            if not self._is_active_category_or_unknown(b.category):
                continue
            spent = by_cat.get(b.category, 0.0)
            pct = (spent / b.limit_amount * 100.0) if b.limit_amount else 0.0

            if pct >= 100.0:
                alerts.append((b.category, spent, b.limit_amount, pct, "over"))
            elif pct >= 80.0:
                alerts.append((b.category, spent, b.limit_amount, pct, "warn"))
            elif pct < 80.0:
                alerts.append((b.category, spent, b.limit_amount, pct, "ok"))

        return alerts

