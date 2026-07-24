"""
Debt data access layer.

Handles creation, payments, modification, deletion, and total debt.
Now supports debt types:
- utility
- credit
- loan
- other
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .database import Database


@dataclass
class Debt:
    """Domain model for a debt item."""
    id: Optional[int]
    name: str
    original: float
    remaining: float
    type: str = "other"  # NEW: debt type with backward-compatible default


class DebtRepository:
    """Repository for interacting with the debts table."""

    VALID_TYPES = {"utility", "credit", "loan", "other"}

    def __init__(self, db: Database) -> None:
        self.db = db
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """
        Ensure the debts table has a 'type' column.
        If not, add it with default 'other'.

        This keeps existing databases and JSON-imported data working.
        """
        cur = self.db.conn.execute("PRAGMA table_info(debts);")
        cols = [row["name"] for row in cur.fetchall()]

        if "type" not in cols:
            self.db.conn.execute(
                "ALTER TABLE debts ADD COLUMN type TEXT DEFAULT 'other';"
            )
            self.db.conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, name: str, amount: float, type: str = "other") -> int:
        """
        Add a new debt with original = remaining = amount.
        Includes a debt type (utility, credit, loan, other).
        """
        type = self._normalize_type(type)

        cur = self.db.conn.cursor()
        cur.execute(
            """
            INSERT INTO debts (name, original, remaining, type)
            VALUES (?, ?, ?, ?);
            """,
            (name, amount, amount, type),
        )
        self.db.conn.commit()
        return int(cur.lastrowid)

    def all(self) -> List[Debt]:
        """Return all debts."""
        cur = self.db.conn.execute(
            "SELECT * FROM debts ORDER BY id ASC;"
        )
        return [self._row_to_debt(row) for row in cur.fetchall()]

    def apply_payment(self, debt_id: int, amount: float) -> None:
        """
        Apply a payment to a debt, reducing remaining but never below zero.
        """
        self.db.conn.execute(
            """
            UPDATE debts
            SET remaining = MAX(0, remaining - ?)
            WHERE id = ?;
            """,
            (amount, debt_id),
        )
        self.db.conn.commit()

    def delete(self, debt_id: int) -> None:
        """Delete a debt by ID."""
        self.db.conn.execute("DELETE FROM debts WHERE id = ?;", (debt_id,))
        self.db.conn.commit()

    def modify(
        self,
        debt_id: int,
        new_name: str,
        new_amount: float,
        new_type: Optional[str] = None,
    ) -> None:
        """
        Modify a debt so that both original and remaining become the new amount.
        Optionally update the debt type.

        This matches your requirement: when a new bill arrives, you overwrite
        the previous state and treat this as the current total due.
        """
        if new_type is not None:
            new_type = self._normalize_type(new_type)
            self.db.conn.execute(
                """
                UPDATE debts
                SET name = ?, original = ?, remaining = ?, type = ?
                WHERE id = ?;
                """,
                (new_name, new_amount, new_amount, new_type, debt_id),
            )
        else:
            self.db.conn.execute(
                """
                UPDATE debts
                SET name = ?, original = ?, remaining = ?
                WHERE id = ?;
                """,
                (new_name, new_amount, new_amount, debt_id),
            )
        self.db.conn.commit()

    def total_debt(self) -> float:
        """Return the sum of remaining amounts across all debts."""
        cur = self.db.conn.execute(
            "SELECT COALESCE(SUM(remaining), 0) AS total FROM debts;"
        )
        row = cur.fetchone()
        return float(row["total"]) if row else 0.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_type(self, t: str) -> str:
        """Normalize and validate a debt type; fallback to 'other'."""
        t = (t or "").strip().lower()
        return t if t in self.VALID_TYPES else "other"

    @staticmethod
    def _infer_type_from_name(name: str) -> str:
        """
        Infer a debt type from its name for backward compatibility
        when older data has no explicit type.
        """
        n = name.lower()

        # Utility heuristics
        if any(x in n for x in ["dte", "we energies", "electric", "gas", "water", "utility"]):
            return "utility"

        # Credit card heuristics
        if "card" in n or "visa" in n or "mastercard" in n:
            return "credit"

        # Loan heuristics
        if "loan" in n or "mortgage" in n or "auto" in n:
            return "loan"

        return "other"

    @staticmethod
    def _row_to_debt(row: "sqlite3.Row") -> Debt:  # type: ignore[name-defined]
        """Convert a SQLite row to a Debt object, with backward compatibility."""
        # Some older rows may not have 'type' or may have it null
        type_value = row["type"] if "type" in row.keys() else None
        if not type_value:
            type_value = DebtRepository._infer_type_from_name(row["name"])

        return Debt(
            id=row["id"],
            name=row["name"],
            original=float(row["original"]),
            remaining=float(row["remaining"]),
            type=type_value,
        )
