"""
Category Helpers - Category Constants

This module contains category constants used throughout the application.

Used by:
- transaction parsing/categorization flows
- API handlers for category validation
"""

from __future__ import annotations

from typing import List, Optional, Sequence

MANUAL_REVIEW = "MANUAL_REVIEW"

# Predefined category options (spending categories only)
PREDEFINED_CATEGORIES = [
    "Income",
    "Housing & Utilities",
    "Food & Groceries",
    "Transportation",
    "Insurance",
    "Healthcare",
    "Shopping",
    "Entertainment",
    "Travel",
    "Debt Payments",
    "Internal Transfers",
    "Investments",
    "Other",
]

# All valid categories including the sentinel value
ALL_VALID_CATEGORIES = PREDEFINED_CATEGORIES + [MANUAL_REVIEW]

CATEGORY_SYNONYMS = {
    "salary": "Income",
    "wages": "Income",
    "payroll": "Income",
    "rent": "Housing & Utilities",
    "utilities": "Housing & Utilities",
    "groceries": "Food & Groceries",
    "food": "Food & Groceries",
    "restaurant": "Food & Groceries",
    "restaurants": "Food & Groceries",
    "transport": "Transportation",
    "transit": "Transportation",
    "rideshare": "Transportation",
    "medical": "Healthcare",
    "health": "Healthcare",
    "insurance": "Insurance",
    "shopping": "Shopping",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "debt": "Debt Payments",
    "loan": "Debt Payments",
    "credit card payment": "Debt Payments",
    "transfer": "Internal Transfers",
    "transfers": "Internal Transfers",
    "investing": "Investments",
    "investment": "Investments",
    "manual_review": MANUAL_REVIEW,
    "manual review": MANUAL_REVIEW,
}


def get_custom_categories(user_id: str) -> List[str]:
    """Fetch user-defined custom category names from the database."""
    from app.database import CustomCategory, SessionLocal
    db = SessionLocal()
    try:
        rows = (
            db.query(CustomCategory)
            .filter(CustomCategory.user_id == user_id)
            .order_by(CustomCategory.name)
            .all()
        )
        return [row.name for row in rows]
    finally:
        db.close()


def get_all_categories(user_id: Optional[str] = None) -> List[str]:
    """Return predefined + user's custom categories (excludes MANUAL_REVIEW)."""
    custom = get_custom_categories(user_id) if user_id else []
    return PREDEFINED_CATEGORIES + custom


def normalize_category(
    category: str,
    custom_categories: Optional[Sequence[str]] = None,
) -> str | None:
    """Normalize category strings to canonical names, including MANUAL_REVIEW.

    If *custom_categories* is provided, also accepts those names as valid.
    """
    if not category or not isinstance(category, str):
        return None
    cleaned = category.strip()
    if not cleaned:
        return None
    if cleaned.upper() == MANUAL_REVIEW:
        return MANUAL_REVIEW
    for canonical in PREDEFINED_CATEGORIES:
        if cleaned.lower() == canonical.lower():
            return canonical
    synonym = CATEGORY_SYNONYMS.get(cleaned.lower())
    if synonym:
        return synonym
    if custom_categories:
        for custom in custom_categories:
            if cleaned.lower() == custom.lower():
                return custom
    return None


def is_valid_category(
    category: str,
    custom_categories: Optional[Sequence[str]] = None,
) -> bool:
    """Return True if category is a known canonical category (including MANUAL_REVIEW)."""
    return normalize_category(category, custom_categories=custom_categories) is not None
