"""
Transactions data access layer.

Handles CRUD for transactions and summary helpers like running total,
month summaries, weekly summaries, and savings‑related queries.

Savings behavior is fully derived from transactions:
- Moving to savings:  type='expense', category='Savings', move_to_savings=1
- Spending from savings: type='savings_spend', spend_from_savings=1
No compensating income is created.

Now supports:
- debt_payment transaction type
- backward‑compatible mapping for legacy "Debt Payment" category
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Union, Dict, Any

import sqlite3

from .database import Database


@dataclass
class Transaction:
    """Domain model for a transaction."""
    id: Optional[int]
    type: str                 # 'income', 'expense', 'savings_spend', 'debt_payment'
    category: str
    vendor: str
    amount: float
    date: str                 # ISO 'YYYY-MM-DD'
    description: str
    move_to_savings: bool
    spend_from_savings: bool
    savings_bucket: Optional[str]


class TransactionRepository:
    """Repository for interacting with the transactions table."""

    VALID_EXPENSE_TYPES = {"expense", "savings_spend", "debt_payment"}

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # INTERNAL NORMALIZATION
    # ------------------------------------------------------------------

    def _normalize_type_and_category(self, t_type: str, category: str) -> tuple[str, str]:
        """
        Normalize transaction type/category for backward compatibility.

        - Legacy: category == "Debt Payment" → treat as debt_payment
        - New: type == "debt_payment" → always treated as an expense for summaries
        """
        t_type = t_type.strip().lower()
        category = category.strip()

        # Legacy compatibility
        if category.lower() == "debt payment":
            return "debt_payment", category

        return t_type, category

    # ------------------------------------------------------------------
    # INSERT
    # ------------------------------------------------------------------

    def add_transaction(self, tx: Union[Transaction, Dict[str, Any]]) -> int:
        """
        Insert a new transaction and return its ID.

        Accepts either:
        - Transaction dataclass
        - dict with keys: type, category, amount, date, description, savings_meta
        """
        if isinstance(tx, dict):
            meta = tx.get("savings_meta", {}) or {}
            move = bool(meta.get("move_to_savings"))
            spend = bool(meta.get("spend_from_savings"))
            bucket = meta.get("bucket")
            t_type = tx["type"]
            category = tx["category"]
            vendor = (tx.get("vendor", "") or "").strip()
            amount = float(tx["amount"])
            date_str = tx["date"]
            desc = tx.get("description", "") or ""
        else:
            move = tx.move_to_savings
            spend = tx.spend_from_savings
            bucket = tx.savings_bucket
            t_type = tx.type
            category = tx.category
            vendor = (tx.vendor or "").strip()
            amount = tx.amount
            date_str = tx.date
            desc = tx.description

        # Normalize for backward compatibility
        t_type, category = self._normalize_type_and_category(t_type, category)

        cur = self.db.conn.cursor()
        cur.execute(
            """
            INSERT INTO transactions (
                type, category, vendor, amount, date, description,
                move_to_savings, spend_from_savings, savings_bucket
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                t_type,
                category,
                vendor,
                amount,
                date_str,
                desc,
                1 if move else 0,
                1 if spend else 0,
                bucket,
            ),
        )
        self.db.conn.commit()
        return int(cur.lastrowid)

    # Backwards compatibility
    def add(self, tx: Union[Transaction, Dict[str, Any]]) -> int:
        return self.add_transaction(tx)

    # ------------------------------------------------------------------
    # GET / DELETE
    # ------------------------------------------------------------------

    def get(self, tx_id: int) -> Optional[Transaction]:
        """Return a single transaction by ID."""
        cur = self.db.conn.execute(
            "SELECT * FROM transactions WHERE id = ?;",
            (tx_id,),
        )
        row = cur.fetchone()
        return self._row_to_tx(row) if row else None

    def delete(self, tx_id: int) -> None:
        """Delete a transaction by ID."""
        self.db.conn.execute("DELETE FROM transactions WHERE id = ?;", (tx_id,))
        self.db.conn.commit()

    def update_transaction(self, tx_id: int, updates: Dict[str, Any]) -> bool:
        """
        Update editable transaction fields for an existing row.

        Editable fields:
        - type
        - category
        - vendor
        - amount
        - date
        - description
        """
        t_type = str(updates.get("type", "")).strip().lower()
        category = str(updates.get("category", "")).strip()
        vendor = str(updates.get("vendor", "") or "").strip()
        amount = float(updates.get("amount", 0.0))
        date_str = str(updates.get("date", "")).strip()
        description = str(updates.get("description", "") or "")

        t_type, category = self._normalize_type_and_category(t_type, category)

        cur = self.db.conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET
                type = ?,
                category = ?,
                vendor = ?,
                amount = ?,
                date = ?,
                description = ?
            WHERE id = ?;
            """,
            (t_type, category, vendor, amount, date_str, description, tx_id),
        )
        self.db.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # SELECT ALL
    # ------------------------------------------------------------------

    def all(self) -> List[Transaction]:
        """Return all transactions ordered by date descending."""
        cur = self.db.conn.execute(
            "SELECT * FROM transactions ORDER BY date DESC, id DESC;"
        )
        return [self._row_to_tx(row) for row in cur.fetchall()]

    def all_transactions(self) -> List[Transaction]:
        """Alias for services that expect this name."""
        return self.all()

    # ------------------------------------------------------------------
    # DATE FILTERS
    # ------------------------------------------------------------------

    def by_month(self, month: int, year: int) -> List[Transaction]:
        """Return all transactions for a given month/year."""
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return self.by_date_range(start, end)

    def by_date_range(self, start: date, end: date) -> List[Transaction]:
        """Return all transactions between two dates inclusive."""
        cur = self.db.conn.execute(
            """
            SELECT * FROM transactions
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC, id ASC;
            """,
            (start.isoformat(), end.isoformat()),
        )
        return [self._row_to_tx(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # SUMMARIES
    # ------------------------------------------------------------------

    def running_total(self) -> float:
        """
        Compute the running total.

        Logic:
        - income         → +amount
        - expense        → -amount
        - debt_payment   → -amount
        - savings_spend  → 0 impact (already left when moved to savings)
        """
        cur = self.db.conn.execute(
            """
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN type = 'income' THEN amount
                        WHEN type = 'expense' THEN -amount
                        WHEN type = 'debt_payment' THEN -amount
                        ELSE 0
                    END
                ), 0) AS total
            FROM transactions;
            """
        )
        row = cur.fetchone()
        return float(row["total"]) if row else 0.0

    def month_summary(self, month: int, year: int) -> dict:
        """
        Return income, expenses, and category/vendor breakdown for a month.

        Includes:
        - expense
        - savings_spend
        - debt_payment
        """
        txs = self.by_month(month, year)

        income = sum(t.amount for t in txs if t.type == "income")

        expenses = sum(
            t.amount for t in txs
            if t.type in ("expense", "savings_spend", "debt_payment")
        )

        by_cat: Dict[str, float] = {}
        by_vendor: Dict[str, float] = {}
        for t in txs:
            if t.type in ("expense", "savings_spend", "debt_payment"):
                by_cat[t.category] = by_cat.get(t.category, 0.0) + t.amount
                vendor = (t.vendor or "").strip() or "Unspecified"
                by_vendor[vendor] = by_vendor.get(vendor, 0.0) + t.amount

        return {
            "income": income,
            "expenses": expenses,
            "by_cat": by_cat,
            "by_vendor": by_vendor,
        }

    def vendor_suggestions(self, tx_type: Optional[str] = None) -> List[str]:
        """
        Return distinct vendor/source names filtered by transaction mode.

        Modes:
        - tx_type == 'income': only income sources
        - tx_type == 'expense': any non-income vendors
        - otherwise: all vendor/source values
        """
        base_sql = """
            SELECT DISTINCT TRIM(COALESCE(vendor, '')) AS vendor_name
            FROM transactions
            WHERE TRIM(COALESCE(vendor, '')) <> ''
        """
        params: tuple[Any, ...] = ()

        if tx_type == "income":
            base_sql += " AND type = ?"
            params = (tx_type,)
        elif tx_type == "expense":
            base_sql += " AND type <> 'income'"
        elif tx_type:
            base_sql += " AND type = ?"
            params = (tx_type,)

        base_sql += " ORDER BY vendor_name COLLATE NOCASE ASC;"
        rows = self.db.conn.execute(base_sql, params).fetchall()
        return [str(row["vendor_name"]) for row in rows]

    def week_expenses(self) -> float:
        """Return total expenses for the current week (Mon–Sun)."""
        today = datetime.today().date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        txs = self.by_date_range(monday, sunday)

        return sum(
            t.amount for t in txs
            if t.type in ("expense", "savings_spend", "debt_payment")
        )

    # ------------------------------------------------------------------
    # SAVINGS HELPERS
    # ------------------------------------------------------------------

    def transactions_for_savings(self) -> List[Transaction]:
        """
        Return all transactions that affect savings.

        Includes:
        - move_to_savings = 1
        - spend_from_savings = 1
        - type='savings_spend'
        - legacy: type='expense' AND category='Savings'
        """
        cur = self.db.conn.execute(
            """
            SELECT * FROM transactions
            WHERE move_to_savings = 1
               OR spend_from_savings = 1
               OR type = 'savings_spend'
               OR (type = 'expense' AND category = 'Savings')
            ORDER BY date ASC, id ASC;
            """
        )
        return [self._row_to_tx(row) for row in cur.fetchall()]

    def transactions_with_savings_flags(self) -> List[Transaction]:
        return self.transactions_for_savings()

    def savings_transactions(self) -> List[Transaction]:
        return self.transactions_for_savings()

    # ------------------------------------------------------------------
    # HISTORY
    # ------------------------------------------------------------------

    def history(self) -> List[Transaction]:
        """Return all transactions oldest → newest."""
        cur = self.db.conn.execute(
            "SELECT * FROM transactions ORDER BY date ASC, id ASC;"
        )
        return [self._row_to_tx(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_tx(row: sqlite3.Row) -> Transaction:
        """Convert a SQLite row to a Transaction object."""
        return Transaction(
            id=row["id"],
            type=row["type"],
            category=row["category"],
            vendor=(row["vendor"] or "") if "vendor" in row.keys() else "",
            amount=float(row["amount"]),
            date=row["date"],
            description=row["description"] or "",
            move_to_savings=bool(row["move_to_savings"]),
            spend_from_savings=bool(row["spend_from_savings"]),
            savings_bucket=row["savings_bucket"],
        )
