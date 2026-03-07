"""
Save Budget Tool - Save user-defined budget targets

This module provides functionality to save and update budget targets for categories.
Budgets can be set as defaults (no month_year) or for specific months.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.database import SessionLocal, Budget, resolve_user_id
from app.logger import classify_error, create_logger
from app.tools.category_helpers import PREDEFINED_CATEGORIES
from app.utils import decimal_to_float

# Create logger for this module
logger = create_logger("save_budget")


async def save_budget_handler(
    budgets: List[Dict[str, Any]],
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save or update budget targets for categories.

    Args:
        budgets: List of budget objects with:
            - category (required): Category name (must match predefined categories)
            - amount (required): Budget target amount (positive number)
            - month_year (optional): Specific month in YYYY-MM format, or null for default
            - currency (optional): Currency code, defaults to USD
        user_id: Optional user ID (defaults to test user)

    Returns:
        Dict with:
        - structuredContent: Summary of saved budgets
        - content: Text confirmation for ChatGPT
    """
    started_at = logger.tool_call_start(
        "save_budget",
        {"budget_count": len(budgets), "user_id": user_id},
    )

    db = SessionLocal()
    try:
        resolved_user_id = resolve_user_id(user_id)

        created_count = 0
        updated_count = 0
        errors = []
        saved_budgets = []

        for budget_input in budgets:
            category = budget_input.get("category", "").strip()
            amount = budget_input.get("amount")
            # Normalize empty string to None for default budgets
            month_year_raw = budget_input.get("month_year")
            month_year = month_year_raw.strip() if isinstance(month_year_raw, str) and month_year_raw.strip() else None
            currency = budget_input.get("currency", "USD").upper()

            # Validate category
            if category not in PREDEFINED_CATEGORIES:
                errors.append(f"Invalid category: {category}")
                continue

            # Validate amount
            if amount is None or not isinstance(amount, (int, float)):
                errors.append(f"Invalid amount for {category}: {amount}")
                continue

            # Ensure amount is positive (budgets are targets, not actual spending)
            amount = abs(float(amount))

            # Validate month_year format if provided (YYYY-MM with 01-12)
            if month_year:
                try:
                    year_str, month_str = month_year.split("-")
                    year_ok = len(year_str) == 4 and year_str.isdigit()
                    month_ok = month_str.isdigit() and 1 <= int(month_str) <= 12 and len(month_str) == 2
                    if not (year_ok and month_ok):
                        errors.append(f"Invalid month_year format for {category}: {month_year} (expected YYYY-MM)")
                        continue
                except ValueError:
                    errors.append(f"Invalid month_year format for {category}: {month_year} (expected YYYY-MM)")
                    continue

            # Check if budget already exists for this category/month
            # NOTE: Unique index doesn't prevent multiple NULLs, so we must check explicitly
            if month_year:
                existing = db.query(Budget).filter(
                    Budget.user_id == resolved_user_id,
                    Budget.category == category,
                    Budget.month_year == month_year,
                ).first()
            else:
                # For default budgets (NULL month_year), explicitly check for NULL
                existing = db.query(Budget).filter(
                    Budget.user_id == resolved_user_id,
                    Budget.category == category,
                    Budget.month_year.is_(None),
                ).first()

            if existing:
                # Update existing budget
                existing.amount = Decimal(str(amount))
                existing.currency = currency
                updated_count += 1
                saved_budgets.append({
                    "id": str(existing.id),
                    "category": category,
                    "amount": amount,
                    "month_year": month_year,
                    "currency": currency,
                    "action": "updated",
                })
            else:
                # Create new budget
                new_budget = Budget(
                    id=str(uuid4()),
                    user_id=resolved_user_id,
                    category=category,
                    amount=Decimal(str(amount)),
                    month_year=month_year,
                    currency=currency,
                )
                db.add(new_budget)
                created_count += 1
                saved_budgets.append({
                    "id": new_budget.id,
                    "category": category,
                    "amount": amount,
                    "month_year": month_year,
                    "currency": currency,
                    "action": "created",
                })

        db.commit()

        # Build response text
        summary_parts = []
        if created_count:
            summary_parts.append(f"{created_count} budget(s) created")
        if updated_count:
            summary_parts.append(f"{updated_count} budget(s) updated")
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")

        summary_text = ", ".join(summary_parts) if summary_parts else "No changes made"

        logger.tool_call_end("save_budget", started_at, {
            "created": created_count,
            "updated": updated_count,
            "errors": len(errors),
        })

        return {
            "structuredContent": {
                "kind": "budget_save_result",
                "created": created_count,
                "updated": updated_count,
                "errors": errors,
                "saved_budgets": saved_budgets,
            },
            "content": [
                {
                    "type": "text",
                    "text": f"Budget update: {summary_text}",
                }
            ],
        }

    except Exception as e:
        logger.tool_call_error(
            "save_budget",
            started_at,
            e,
            classify_error(e),
        )
        db.rollback()
        raise

    finally:
        db.close()


# NOTE: This handler is no longer exposed via a separate tool surface.
# Budget data is accessed via API endpoints and get_financial_data.