"""
Database module for Budget Planner.

Provides:
- A single SQLite connection
- Schema creation
- Automatic migration to remove old CHECK(type IN (...)) constraint
- Optional migration from legacy JSON (budget_data.json)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


JSON_FILENAME = "budget_data.json"


import sys
import os

def get_database_path(filename: str) -> Path:
    """
    Returns a safe, writable path for the database.
    - In development: store next to the source file
    - In PyInstaller EXE: store in %LOCALAPPDATA%/BudgetPlanner/
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller EXE
        base = Path(os.environ["LOCALAPPDATA"]) / "BudgetPlanner"
    else:
        # Running from source
        base = Path(__file__).resolve().parent

    base.mkdir(parents=True, exist_ok=True)
    return base / filename


class Database:
    """
    SQLite database wrapper.

    Accepts a string path to the database file.
    Creates parent directories if needed.
    Creates schema if missing.
    Performs automatic migration if old constraints exist.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = get_database_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create connection
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

        self._enable_foreign_keys()
        self._create_schema()
        self._ensure_categories_schema()
        self._migrate_transactions_table()   # <-- FIXES THE CHECK CONSTRAINT
        self._ensure_transactions_vendor_column()

        # Optional migration from legacy JSON
        self._maybe_migrate_from_json()

    # ------------------------------------------------------------------
    # Connection property
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    # ------------------------------------------------------------------
    # Foreign Keys
    # ------------------------------------------------------------------

    def _enable_foreign_keys(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON;")

    # ------------------------------------------------------------------
    # Schema Creation
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        """Create all required tables if they do not exist."""
        cur = self._conn.cursor()

        # Transactions (new schema — no CHECK constraint)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                vendor TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL CHECK (amount > 0),
                date TEXT NOT NULL,
                description TEXT,
                move_to_savings INTEGER NOT NULL DEFAULT 0,
                spend_from_savings INTEGER NOT NULL DEFAULT 0,
                savings_bucket TEXT
            );
            """
        )

        # Debts (now includes type)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                original REAL NOT NULL CHECK (original >= 0),
                remaining REAL NOT NULL CHECK (remaining >= 0),
                type TEXT NOT NULL DEFAULT 'other'
            );
            """
        )

        # Budgets
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                limit_amount REAL NOT NULL CHECK (limit_amount > 0)
            );
            """
        )

        # Categories
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                advisor_group TEXT NOT NULL DEFAULT 'wants'
                    CHECK (advisor_group IN ('needs', 'wants', 'financial')),
                debt_type TEXT,
                is_savings INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                UNIQUE(name, kind)
            );
            """
        )

        # Category suggestions discovered from legacy/history data.
        # These are not active categories until the user explicitly imports them.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS category_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                source TEXT NOT NULL DEFAULT 'transactions',
                ignored INTEGER NOT NULL DEFAULT 0,
                UNIQUE(kind, normalized_name)
            );
            """
        )

        self._conn.commit()

    # ------------------------------------------------------------------
    # MIGRATION: Remove old CHECK constraint
    # ------------------------------------------------------------------

    def _migrate_transactions_table(self) -> None:
        """
        Detects if the old CHECK(type IN ('income','expense')) constraint exists.
        If so, performs a full table migration to the new flexible schema.
        """

        cur = self._conn.cursor()

        # Get the SQL that created the transactions table
        row = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions';"
        ).fetchone()

        if not row or not row["sql"]:
            return

        sql = row["sql"]

        # If the old CHECK constraint is present, migrate
        if "CHECK (type IN ('income', 'expense'))" in sql or \
           "CHECK(type IN ('income','expense'))" in sql:

            print("Migrating transactions table to remove CHECK constraint...")

            # 1. Rename old table
            cur.execute("ALTER TABLE transactions RENAME TO transactions_old;")

            # 2. Create new table with updated schema
            cur.execute(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    vendor TEXT NOT NULL DEFAULT '',
                    amount REAL NOT NULL CHECK (amount > 0),
                    date TEXT NOT NULL,
                    description TEXT,
                    move_to_savings INTEGER NOT NULL DEFAULT 0,
                    spend_from_savings INTEGER NOT NULL DEFAULT 0,
                    savings_bucket TEXT
                );
                """
            )

            # 3. Copy data from old → new
            cur.execute(
                """
                INSERT INTO transactions (
                    id, type, category, vendor, amount, date, description,
                    move_to_savings, spend_from_savings, savings_bucket
                )
                SELECT
                    id, type, category, '', amount, date, description,
                    move_to_savings, spend_from_savings, savings_bucket
                FROM transactions_old;
                """
            )

            # 4. Drop old table
            cur.execute("DROP TABLE transactions_old;")

            self._conn.commit()

    def _ensure_transactions_vendor_column(self) -> None:
        """Add transactions.vendor to existing databases if missing."""
        cur = self._conn.cursor()
        info_rows = cur.execute("PRAGMA table_info(transactions);").fetchall()
        existing_cols = {row["name"] for row in info_rows}

        if "vendor" not in existing_cols:
            cur.execute("ALTER TABLE transactions ADD COLUMN vendor TEXT NOT NULL DEFAULT '';")
            self._conn.commit()

    def _ensure_categories_schema(self) -> None:
        """Add category columns introduced after initial release."""
        cur = self._conn.cursor()
        info_rows = cur.execute("PRAGMA table_info(categories);").fetchall()
        existing_cols = {row["name"] for row in info_rows}

        if not existing_cols:
            return

        if "active" not in existing_cols:
            cur.execute("ALTER TABLE categories ADD COLUMN active INTEGER NOT NULL DEFAULT 1;")
            self._conn.commit()

    # ------------------------------------------------------------------
    # JSON Migration
    # ------------------------------------------------------------------

    def _table_empty(self, table: str) -> bool:
        cur = self._conn.execute(f"SELECT COUNT(*) AS c FROM {table};")
        row = cur.fetchone()
        return bool(row) and row["c"] == 0

    def _maybe_migrate_from_json(self) -> None:
        """Migrate from legacy JSON if DB is empty."""
        json_path = self.db_path.parent / JSON_FILENAME
        if not json_path.exists():
            return

        if not (
            self._table_empty("transactions")
            and self._table_empty("debts")
            and self._table_empty("budgets")
            and self._table_empty("categories")
        ):
            return

        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        self._migrate_transactions(data.get("transactions", []))
        self._migrate_debts(data.get("debt", []))
        self._migrate_budgets(data.get("budgets", {}))

        self._conn.commit()

    def _migrate_transactions(self, txs: Iterable[dict[str, Any]]) -> None:
        sql = """
            INSERT INTO transactions (
                type, category, vendor, amount, date, description,
                move_to_savings, spend_from_savings, savings_bucket
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        for t in txs:
            meta = t.get("savings_meta", {}) or {}
            move = 1 if meta.get("move_to_savings") else 0
            spend = 1 if meta.get("spend_from_savings") else 0
            bucket = meta.get("bucket")

            self._conn.execute(
                sql,
                (
                    t.get("type", "expense"),
                    t.get("category", "Other"),
                    t.get("vendor", ""),
                    float(t.get("amount", 0.0)),
                    t.get("date", ""),
                    t.get("description", ""),
                    move,
                    spend,
                    bucket,
                ),
            )

    @staticmethod
    def _infer_debt_type_from_name(name: str) -> str:
        """
        Infer a debt type from its name for legacy JSON migration.
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

    def _migrate_debts(self, debts: Iterable[dict[str, Any]]) -> None:
        sql = """
            INSERT INTO debts (name, original, remaining, type)
            VALUES (?, ?, ?, ?);
        """
        for d in debts:
            name = d.get("name", "Debt")
            original = float(d.get("original", 0.0))
            remaining = float(d.get("remaining", original))
            debt_type = self._infer_debt_type_from_name(name)
            self._conn.execute(sql, (name, original, remaining, debt_type))

    def _migrate_budgets(self, budgets: dict[str, Any]) -> None:
        sql = """
            INSERT INTO budgets (category, limit_amount)
            VALUES (?, ?);
        """
        for cat, lim in budgets.items():
            self._conn.execute(sql, (cat, float(lim)))

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        self._conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()
