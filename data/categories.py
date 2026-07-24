"""
Categories data access layer.

Provides a live category configuration layer for future behavior while
leaving historical transaction category labels untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .database import Database


@dataclass(frozen=True)
class Category:
    """Domain model for a configured transaction category."""

    id: int
    name: str
    kind: str
    advisor_group: str
    debt_type: Optional[str]
    is_savings: bool
    active: bool
    sort_order: int


@dataclass(frozen=True)
class CategorySuggestion:
    """A potential category discovered from historical data."""

    id: int
    name: str
    kind: str
    source: str
    ignored: bool


CATEGORY_TEMPLATES = [
    ("Housing", "expense", "needs", None, 0, 10),
    ("Groceries", "expense", "needs", None, 0, 20),
    ("Transportation", "expense", "needs", None, 0, 30),
    ("Utilities", "expense", "needs", "utility", 0, 40),
    ("Entertainment", "expense", "wants", None, 0, 50),
    ("Dining Out", "expense", "wants", None, 0, 60),
    ("Healthcare", "expense", "needs", None, 0, 70),
    ("Insurance", "expense", "needs", None, 0, 80),
    ("Education", "expense", "wants", None, 0, 90),
    ("Shopping", "expense", "wants", None, 0, 100),
    ("Personal Care", "expense", "wants", None, 0, 110),
    ("Subscriptions", "expense", "wants", None, 0, 120),
    ("Savings", "expense", "financial", None, 1, 130),
    ("Credit Card Payment", "expense", "financial", "credit", 0, 140),
    ("Loan Payment", "expense", "financial", "loan", 0, 150),
    ("Other", "expense", "wants", "other", 0, 160),
    ("Gifts", "expense", "wants", None, 0, 170),
    ("Snacks", "expense", "wants", None, 0, 180),
    ("Vapes", "expense", "wants", None, 0, 190),
    ("Salary", "income", "wants", None, 0, 200),
    ("Freelance", "income", "wants", None, 0, 210),
    ("Investments", "income", "wants", None, 0, 220),
    ("Gifts", "income", "wants", None, 0, 230),
    ("Refunds", "income", "wants", None, 0, 240),
    ("Side Hustle", "income", "wants", None, 0, 250),
    ("Other", "income", "wants", None, 0, 260),
]


class CategoryRepository:
    """Repository for interacting with the categories table."""

    VALID_KINDS = {"income", "expense"}
    VALID_ADVISOR_GROUPS = {"needs", "wants", "financial"}
    VALID_DEBT_TYPES = {"utility", "credit", "loan", "other"}

    LEGACY_METADATA = {
        "Debt Payment": {
            "kind": "expense",
            "advisor_group": "financial",
            "debt_type": "credit",
            "is_savings": False,
        },
    }

    def __init__(self, db: Database) -> None:
        self.db = db
        self._retire_unused_seeded_categories()
        self._import_existing_categories()
        self._sync_transaction_category_suggestions()

    def all(self, kind: Optional[str] = None, include_inactive: bool = False) -> List[Category]:
        """Return configured categories, optionally filtered by kind."""
        sql = "SELECT * FROM categories"
        clauses: list[str] = []
        params: list[object] = []

        if kind:
            clauses.append("kind = ?")
            params.append(self._normalize_kind(kind))
        if not include_inactive:
            clauses.append("active = 1")

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        sql += " ORDER BY kind ASC, sort_order ASC, LOWER(name) ASC, id ASC;"
        cur = self.db.conn.execute(sql, tuple(params))
        return [self._row_to_category(row) for row in cur.fetchall()]

    def names(self, kind: Optional[str] = None, include_inactive: bool = False) -> List[str]:
        return [category.name for category in self.all(kind, include_inactive=include_inactive)]

    def template_categories(self, kind: Optional[str] = None) -> List[Category]:
        """Return optional template categories that can be imported by the user."""
        templates: List[Category] = []
        for idx, (name, template_kind, advisor_group, debt_type, is_savings, sort_order) in enumerate(CATEGORY_TEMPLATES, start=1):
            if kind and template_kind != self._normalize_kind(kind):
                continue
            templates.append(
                Category(
                    id=-idx,
                    name=name,
                    kind=template_kind,
                    advisor_group=advisor_group,
                    debt_type=debt_type,
                    is_savings=bool(is_savings),
                    active=False,
                    sort_order=sort_order,
                )
            )
        return templates

    def import_templates(self, names: List[str], kind: str) -> List[Category]:
        """Import selected template names as active categories."""
        normalized_kind = self._normalize_kind(kind)
        created: List[Category] = []
        template_lookup = {
            (template_name.lower(), template_kind): (template_name, advisor_group, debt_type, bool(is_savings))
            for template_name, template_kind, advisor_group, debt_type, is_savings, _ in CATEGORY_TEMPLATES
        }

        for raw_name in names:
            name = (raw_name or "").strip()
            if not name:
                continue
            key = (name.lower(), normalized_kind)
            if key not in template_lookup:
                continue
            template_name, advisor_group, debt_type, is_savings = template_lookup[key]
            created.append(
                self.ensure_category(
                    template_name,
                    normalized_kind,
                    advisor_group=advisor_group,
                    debt_type=debt_type,
                    is_savings=is_savings,
                    active=True,
                )
            )
        return created

    def available_template_names(self, kind: str) -> List[str]:
        """Return template names that are not currently active for this kind."""
        normalized_kind = self._normalize_kind(kind)
        names: List[str] = []
        for template_name, template_kind, *_ in CATEGORY_TEMPLATES:
            if template_kind != normalized_kind:
                continue
            existing = self.get(template_name, normalized_kind, include_inactive=True)
            if existing is not None and existing.active:
                continue
            names.append(template_name)
        return names

    def list_suggestions(self, kind: Optional[str] = None, include_ignored: bool = False) -> List[CategorySuggestion]:
        """Return discovered category suggestions that are not active categories."""
        sql = "SELECT id, name, kind, source, ignored FROM category_suggestions"
        clauses: list[str] = []
        params: list[object] = []

        if kind:
            clauses.append("kind = ?")
            params.append(self._normalize_kind(kind))
        if not include_ignored:
            clauses.append("ignored = 0")

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        sql += " ORDER BY kind ASC, LOWER(name) ASC, id ASC;"
        rows = self.db.conn.execute(sql, tuple(params)).fetchall()
        suggestions = [self._row_to_suggestion(row) for row in rows]

        filtered: List[CategorySuggestion] = []
        for suggestion in suggestions:
            existing = self.get(suggestion.name, suggestion.kind, include_inactive=False)
            if existing is not None:
                continue
            filtered.append(suggestion)
        return filtered

    def import_suggestion(
        self,
        name: str,
        kind: str,
        *,
        advisor_group: Optional[str] = None,
        debt_type: Optional[str] = None,
        is_savings: Optional[bool] = None,
    ) -> Category:
        """Promote a suggestion to an active category."""
        category = self.ensure_category(
            name,
            kind,
            advisor_group=advisor_group,
            debt_type=debt_type,
            is_savings=is_savings,
            active=True,
        )
        self._remove_suggestion(name, kind)
        return category

    def ignore_suggestion(self, name: str, kind: str) -> None:
        """Hide a suggestion from future manager prompts."""
        normalized_kind = self._normalize_kind(kind)
        cleaned = name.strip()
        if not cleaned:
            return
        self.db.conn.execute(
            """
            UPDATE category_suggestions
            SET ignored = 1
            WHERE kind = ? AND normalized_name = ?;
            """,
            (normalized_kind, cleaned.lower()),
        )
        self.db.conn.commit()

    def expense_categories(self, include_inactive: bool = False) -> List[Category]:
        return self.all("expense", include_inactive=include_inactive)

    def income_categories(self, include_inactive: bool = False) -> List[Category]:
        return self.all("income", include_inactive=include_inactive)

    def get(self, name: str, kind: Optional[str] = None, include_inactive: bool = True) -> Optional[Category]:
        """Return a category by name, matching case-insensitively."""
        cleaned = name.strip()
        if not cleaned:
            return None

        sql = "SELECT * FROM categories WHERE LOWER(name) = LOWER(?)"
        params: list[object] = [cleaned]
        if kind:
            sql += " AND kind = ?"
            params.append(self._normalize_kind(kind))
        if not include_inactive:
            sql += " AND active = 1"
        sql += " ORDER BY id ASC LIMIT 1;"
        row = self.db.conn.execute(sql, tuple(params)).fetchone()
        return self._row_to_category(row) if row else None

    def ensure_category(
        self,
        name: str,
        kind: str,
        *,
        advisor_group: Optional[str] = None,
        debt_type: Optional[str] = None,
        is_savings: Optional[bool] = None,
        active: bool = True,
    ) -> Category:
        """Return an existing category or create/reactivate it with inferred metadata."""
        normalized_kind = self._normalize_kind(kind)
        existing = self.get(name, normalized_kind, include_inactive=True)
        if existing is not None:
            updated = self.update_category(
                existing.name,
                normalized_kind,
                advisor_group=advisor_group,
                debt_type=debt_type,
                is_savings=is_savings,
                active=active,
            )
            self._remove_suggestion(existing.name, normalized_kind)
            self._remove_suggestion(name, normalized_kind)
            return updated

        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Category name is required.")

        metadata = self._resolve_metadata(
            name=cleaned,
            kind=normalized_kind,
            advisor_group=advisor_group,
            debt_type=debt_type,
            is_savings=is_savings,
        )
        next_order = self._next_sort_order(normalized_kind)

        self.db.conn.execute(
            """
            INSERT INTO categories (name, kind, advisor_group, debt_type, is_savings, active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                cleaned,
                normalized_kind,
                metadata["advisor_group"],
                metadata["debt_type"],
                1 if metadata["is_savings"] else 0,
                1 if active else 0,
                next_order,
            ),
        )
        self.db.conn.commit()

        created = self.get(cleaned, normalized_kind, include_inactive=True)
        if created is None:
            raise RuntimeError("Failed to create category.")
        self._remove_suggestion(cleaned, normalized_kind)
        return created

    def add_category(self, name: str, kind: str) -> Category:
        return self.ensure_category(name, kind)

    def update_category(
        self,
        current_name: str,
        kind: str,
        *,
        new_name: Optional[str] = None,
        advisor_group: Optional[str] = None,
        debt_type: Optional[str] = None,
        is_savings: Optional[bool] = None,
        active: Optional[bool] = None,
    ) -> Category:
        """Update category metadata without rewriting historical transactions."""
        normalized_kind = self._normalize_kind(kind)
        current = self.get(current_name, normalized_kind, include_inactive=True)
        if current is None:
            raise ValueError("Category not found.")

        replacement = (new_name or current.name).strip()
        if not replacement:
            raise ValueError("Category name is required.")

        conflict = self.get(replacement, normalized_kind, include_inactive=True)
        if conflict is not None and conflict.id != current.id:
            raise ValueError("A category with that name already exists.")

        metadata = self._resolve_metadata(
            name=replacement,
            kind=normalized_kind,
            advisor_group=current.advisor_group if advisor_group is None else advisor_group,
            debt_type=current.debt_type if debt_type is None else debt_type,
            is_savings=current.is_savings if is_savings is None else is_savings,
        )
        active_value = current.active if active is None else bool(active)

        with self.db.conn:
            self.db.conn.execute(
                """
                UPDATE categories
                SET name = ?, advisor_group = ?, debt_type = ?, is_savings = ?, active = ?
                WHERE id = ?;
                """,
                (
                    replacement,
                    metadata["advisor_group"],
                    metadata["debt_type"],
                    1 if metadata["is_savings"] else 0,
                    1 if active_value else 0,
                    current.id,
                ),
            )
            if replacement != current.name:
                self.db.conn.execute(
                    "UPDATE budgets SET category = ? WHERE category = ?;",
                    (replacement, current.name),
                )

        updated = self.get(replacement, normalized_kind, include_inactive=True)
        if updated is None:
            raise RuntimeError("Failed to update category.")
        return updated

    def rename_category(self, old_name: str, new_name: str, kind: Optional[str] = None) -> Category:
        current = self.get(old_name, kind, include_inactive=True)
        if current is None:
            raise ValueError("Category not found.")
        return self.update_category(current.name, current.kind, new_name=new_name)

    def delete_category(self, name: str, kind: str) -> None:
        """Deactivate a category so history remains visible but future entry hides it."""
        current = self.get(name, kind, include_inactive=True)
        if current is None:
            raise ValueError("Category not found.")

        with self.db.conn:
            self.db.conn.execute(
                "UPDATE categories SET active = 0 WHERE id = ?;",
                (current.id,),
            )

    def reactivate_category(self, name: str, kind: str) -> Category:
        """Reactivate an inactive category without changing historical transactions."""
        return self.ensure_category(name, kind, active=True)

    def default_category_for_debt_type(self, debt_type: str) -> Optional[str]:
        row = self.db.conn.execute(
            """
            SELECT name
            FROM categories
            WHERE kind = 'expense' AND debt_type = ? AND active = 1
            ORDER BY sort_order ASC, id ASC
            LIMIT 1;
            """,
            (self._normalize_debt_type(debt_type),),
        ).fetchone()
        return str(row["name"]) if row else None

    def expense_names_by_group(self, advisor_group: str) -> List[str]:
        cur = self.db.conn.execute(
            """
            SELECT name
            FROM categories
            WHERE kind = 'expense' AND advisor_group = ? AND active = 1
            ORDER BY sort_order ASC, LOWER(name) ASC, id ASC;
            """,
            (self._normalize_advisor_group(advisor_group),),
        )
        return [str(row["name"]) for row in cur.fetchall()]

    def is_savings_category(self, name: str) -> bool:
        category = self.get(name, "expense")
        return bool(category and category.is_savings and category.active)

    def debt_type_for_category(self, name: str) -> Optional[str]:
        category = self.get(name, "expense")
        if category is None or not category.active:
            return None
        return category.debt_type

    def _import_existing_categories(self) -> None:
        budget_rows = list(self.db.conn.execute("SELECT DISTINCT category FROM budgets WHERE TRIM(category) <> '';"))
        debt_rows = list(self.db.conn.execute("SELECT DISTINCT name, type FROM debts WHERE TRIM(name) <> '';"))

        for row in budget_rows:
            category_name = str(row["category"] or "").strip()
            if not category_name:
                continue
            self._import_category_if_missing(category_name, "expense")

        for row in debt_rows:
            debt_name = str(row["name"] or "").strip()
            debt_type = str(row["type"] or "other").strip().lower()
            if not debt_name:
                continue
            advisor_group = "needs" if debt_type == "utility" else "financial"
            self._import_category_if_missing(
                debt_name,
                "expense",
                advisor_group=advisor_group,
                debt_type=debt_type,
                is_savings=False,
            )

    def _sync_transaction_category_suggestions(self) -> None:
        """Discover transaction labels without forcing them into active categories."""
        rows = list(
            self.db.conn.execute(
                """
                SELECT DISTINCT category, type
                FROM transactions
                WHERE TRIM(category) <> '';
                """
            )
        )

        for row in rows:
            category_name = str(row["category"] or "").strip()
            tx_type = str(row["type"] or "").strip().lower()
            if not category_name:
                continue

            kind = "income" if tx_type == "income" else "expense"
            if self.get(category_name, kind, include_inactive=True) is not None:
                continue

            self._save_suggestion(category_name, kind, source="transactions")

    def _retire_unused_seeded_categories(self) -> None:
        """Deactivate old seeded categories that are not backed by user data."""
        default_names = {(name, kind) for name, kind, *_ in CATEGORY_TEMPLATES}
        for category in self.all(include_inactive=True):
            key = (category.name, category.kind)
            if key not in default_names or not category.active:
                continue
            if self._category_has_usage(category):
                continue
            self.db.conn.execute(
                "UPDATE categories SET active = 0 WHERE id = ?;",
                (category.id,),
            )
        self.db.conn.commit()

    def _import_category_if_missing(
        self,
        name: str,
        kind: str,
        *,
        advisor_group: Optional[str] = None,
        debt_type: Optional[str] = None,
        is_savings: Optional[bool] = None,
    ) -> None:
        existing = self.get(name, kind, include_inactive=True)
        if existing is not None:
            return
        self.ensure_category(
            name,
            kind,
            advisor_group=advisor_group,
            debt_type=debt_type,
            is_savings=is_savings,
            active=True,
        )

    def _category_has_usage(self, category: Category) -> bool:
        if self.db.conn.execute(
            "SELECT 1 FROM transactions WHERE category = ? LIMIT 1;",
            (category.name,),
        ).fetchone():
            return True

        if category.kind == "expense":
            if self.db.conn.execute(
                "SELECT 1 FROM budgets WHERE category = ? LIMIT 1;",
                (category.name,),
            ).fetchone():
                return True
            if self.db.conn.execute(
                "SELECT 1 FROM debts WHERE LOWER(name) = LOWER(?) LIMIT 1;",
                (category.name,),
            ).fetchone():
                return True

        return False

    def _resolve_metadata(
        self,
        *,
        name: str,
        kind: str,
        advisor_group: Optional[str],
        debt_type: Optional[str],
        is_savings: Optional[bool],
    ) -> dict[str, object]:
        metadata = self._metadata_for_name(name, kind)

        if kind == "income":
            metadata["advisor_group"] = "wants"
            metadata["debt_type"] = None
            metadata["is_savings"] = False
            return metadata

        if advisor_group is not None:
            metadata["advisor_group"] = self._normalize_advisor_group(advisor_group)
        if debt_type is not None:
            metadata["debt_type"] = self._normalize_debt_type(debt_type)
        if is_savings is not None:
            metadata["is_savings"] = bool(is_savings)

        if metadata["is_savings"]:
            metadata["advisor_group"] = "financial"
            metadata["debt_type"] = None
        elif metadata["debt_type"] in {"credit", "loan", "other"}:
            metadata["advisor_group"] = "financial"
        elif metadata["debt_type"] == "utility" and advisor_group is None:
            metadata["advisor_group"] = "needs"

        return metadata

    def _metadata_for_name(self, name: str, kind: str) -> dict[str, object]:
        legacy = self.LEGACY_METADATA.get(name)
        if legacy is not None and legacy["kind"] == kind:
            return dict(legacy)

        debt_match = self.db.conn.execute(
            "SELECT type FROM debts WHERE LOWER(name) = LOWER(?) ORDER BY id ASC LIMIT 1;",
            (name.strip(),),
        ).fetchone()
        if debt_match is not None:
            matched_debt_type = self._normalize_debt_type(str(debt_match["type"] or "other"))
            advisor_group = "needs" if matched_debt_type == "utility" else "financial"
            return {
                "advisor_group": advisor_group,
                "debt_type": matched_debt_type,
                "is_savings": False,
            }

        if kind == "expense" and name.strip().lower() == "savings":
            return {"advisor_group": "financial", "debt_type": None, "is_savings": True}

        return {"advisor_group": "wants", "debt_type": None, "is_savings": False}

    def _save_suggestion(self, name: str, kind: str, *, source: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return

        normalized_kind = self._normalize_kind(kind)
        self.db.conn.execute(
            """
            INSERT INTO category_suggestions (name, normalized_name, kind, source, ignored)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(kind, normalized_name)
            DO UPDATE SET name = excluded.name, source = excluded.source;
            """,
            (cleaned, cleaned.lower(), normalized_kind, source),
        )
        self.db.conn.commit()

    def _remove_suggestion(self, name: str, kind: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        normalized_kind = self._normalize_kind(kind)
        self.db.conn.execute(
            "DELETE FROM category_suggestions WHERE kind = ? AND normalized_name = ?;",
            (normalized_kind, cleaned.lower()),
        )
        self.db.conn.commit()

    def _normalize_kind(self, kind: str) -> str:
        cleaned = (kind or "").strip().lower()
        if cleaned not in self.VALID_KINDS:
            raise ValueError("Invalid category kind.")
        return cleaned

    def _normalize_advisor_group(self, advisor_group: str) -> str:
        cleaned = (advisor_group or "").strip().lower()
        if cleaned not in self.VALID_ADVISOR_GROUPS:
            raise ValueError("Invalid category group.")
        return cleaned

    def _normalize_debt_type(self, debt_type: str) -> str:
        cleaned = (debt_type or "").strip().lower()
        if cleaned not in self.VALID_DEBT_TYPES:
            raise ValueError("Invalid debt type.")
        return cleaned

    def _next_sort_order(self, kind: str) -> int:
        row = self.db.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS max_order FROM categories WHERE kind = ?;",
            (kind,),
        ).fetchone()
        max_order = int(row["max_order"]) if row else 0
        return max_order + 10

    @staticmethod
    def _row_to_category(row) -> Category:
        return Category(
            id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            advisor_group=str(row["advisor_group"]),
            debt_type=(str(row["debt_type"]) if row["debt_type"] is not None else None),
            is_savings=bool(row["is_savings"]),
            active=bool(row["active"]),
            sort_order=int(row["sort_order"]),
        )

    @staticmethod
    def _row_to_suggestion(row) -> CategorySuggestion:
        return CategorySuggestion(
            id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            source=str(row["source"]),
            ignored=bool(row["ignored"]),
        )