"""
Savings data access layer.

All savings balances and history are derived from transactions only.
No separate savings table is persisted.

Conventions:
- Moving to savings:
    * type = 'expense' AND category = 'Savings'
      OR move_to_savings = 1
- Spending from savings:
    * type = 'savings_spend'
      OR spend_from_savings = 1
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Tuple

import numpy as np  # type: ignore[import]

from .transactions import TransactionRepository, Transaction


SAVINGS_BUCKETS = ["Savings", "E-Savings"]


@dataclass
class SavingsPoint:
    """Snapshot of savings balances for a given date."""
    date: date
    balances: Dict[str, float]


class SavingsService:
    """
    Service for computing savings balances, totals, and history
    from transactions.
    """

    def __init__(self, tx_repo: TransactionRepository) -> None:
        self.tx_repo = tx_repo

    # ------------------------------------------------------------------
    # BALANCES
    # ------------------------------------------------------------------

    def current_balances(self) -> Dict[str, float]:
        """
        Compute current balances per savings bucket from all transactions.
        """
        history = self.history_points()
        if not history:
            return {b: 0.0 for b in SAVINGS_BUCKETS}
        last_date = next(reversed(history))
        return history[last_date]

    def total_savings(self) -> float:
        """
        Return total savings across all buckets.
        """
        balances = self.current_balances()
        return sum(balances.values())

    # ------------------------------------------------------------------
    # HISTORY RECONSTRUCTION
    # ------------------------------------------------------------------

    def history_points(self) -> "OrderedDict[date, Dict[str, float]]":
        """
        Reconstruct savings balances over time from transactions.

        Returns:
            OrderedDict[date -> {bucket: balance}]
        """
        txs = self.tx_repo.savings_transactions()
        balances: Dict[str, float] = {b: 0.0 for b in SAVINGS_BUCKETS}
        history: "OrderedDict[date, Dict[str, float]]" = OrderedDict()

        # Sort by date (and implicitly by id via repository ordering)
        for t in sorted(txs, key=lambda x: x.date):
            d = datetime.strptime(t.date, "%Y-%m-%d").date()
            bucket = t.savings_bucket or "Savings"

            if bucket not in balances:
                balances[bucket] = 0.0

            # Move to savings:
            # - explicit move_to_savings flag
            # - legacy: expense with category 'Savings'
            if t.move_to_savings or (t.type == "expense" and t.category == "Savings"):
                balances[bucket] += t.amount

            # Spend from savings:
            # - explicit spend_from_savings flag
            # - new canonical type 'savings_spend'
            elif t.spend_from_savings or t.type == "savings_spend":
                balances[bucket] = max(0.0, balances[bucket] - t.amount)

            history[d] = dict(balances)

        return history

    # ------------------------------------------------------------------
    # TABLE VIEW
    # ------------------------------------------------------------------

    def savings_transactions_table(self) -> List[Tuple[str, str, str, float, str, str]]:
        """
        Return savings-related transactions formatted for table display.

        Each row:
        (date, bucket, direction, amount, category, description)

        direction:
        - "To Savings"   for moves into savings
        - "From Savings" for spending from savings
        """
        rows: List[Tuple[str, str, str, float, str, str]] = []
        for t in self.tx_repo.savings_transactions():
            bucket = t.savings_bucket or "Savings"

            if t.move_to_savings or (t.type == "expense" and t.category == "Savings"):
                direction = "To Savings"
            elif t.spend_from_savings or t.type == "savings_spend":
                direction = "From Savings"
            else:
                continue

            rows.append(
                (
                    t.date,
                    bucket,
                    direction,
                    t.amount,
                    t.category,
                    t.description,
                )
            )
        return rows

    # ------------------------------------------------------------------
    # OPTIONAL: SERIES FOR CHARTS
    # ------------------------------------------------------------------

    def series_for_chart(self) -> Tuple[List[str], Dict[str, List[float]]]:
        """
        Return dates and per-bucket series suitable for plotting.

        Returns:
            (dates, {bucket: [balances...]})
        """
        history = self.history_points()
        if not history:
            return [], {b: [] for b in SAVINGS_BUCKETS}

        dates = [d.isoformat() for d in history.keys()]
        buckets = sorted({b for snapshot in history.values() for b in snapshot.keys()})

        series: Dict[str, List[float]] = {b: [] for b in buckets}
        for snapshot in history.values():
            for b in buckets:
                series[b].append(snapshot.get(b, 0.0))

        return dates, series
