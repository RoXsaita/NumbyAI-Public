"""
Mutate Categories Tool - Edit and Transfer Category Amounts

This module provides tools to mutate category totals through adjustment transactions:
1. Edit operations - set a category's total amount directly
2. Transfer operations - move amounts between categories (zero-sum, sign-aware)

TRANSFER SIGN RULES (automatic, zero-sum):
─────────────────────────────────────────────────────────────────────────────────
When transferring $X from Category A to Category B:

• If A is an EXPENSE (negative total, e.g., -500):
  → A increases by X (becomes less negative: -500 → -400)
  → B decreases by X (becomes more negative: -200 → -300)
  → Net change: 0 ✓

• If A is INCOME (positive total, e.g., +1000):
  → A decreases by X (becomes less positive: +1000 → +900)
  → B increases by X (becomes more positive: +200 → +300)
  → Net change: 0 ✓

This preserves statement reconciliation - the sum of all categories remains unchanged.

For SIGN CORRECTIONS (expense→income or vice versa), use two edit operations
since those represent actual changes to the statement's net flow.
─────────────────────────────────────────────────────────────────────────────────

All operations are performed server-side in a transaction to ensure data integrity.
"""

from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Optional

from app.database import SessionLocal, Transaction, resolve_user_id
from app.logger import create_logger, ErrorType
from app.utils import month_year_to_date_range

# Create logger for this module
logger = create_logger("mutate_categories")


def _validate_edit_op(op: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    """Validate an edit operation, returning an error dict or None if valid."""
    category = op.get("category")
    if not category:
        return {"message": f"Operation {idx + 1}: Edit requires 'category' field.", "status": "error", "category": "unknown"}
    if "new_amount" not in op:
        return {"message": f"Operation {idx + 1}: Edit requires 'new_amount' field.", "status": "error", "category": category}
    if not isinstance(op.get("new_amount"), (int, float)):
        return {"message": f"Operation {idx + 1}: 'new_amount' must be a number.", "status": "error", "category": category}
    return None


def _validate_transfer_op(op: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    """Validate a transfer operation, returning an error dict or None if valid."""
    from_cat = op.get("from_category")
    to_cat = op.get("to_category")
    transfer_amount = op.get("transfer_amount")

    if not from_cat:
        return {"message": f"Operation {idx + 1}: Transfer requires 'from_category' field.", "status": "error", "category": "unknown"}
    if not to_cat:
        return {"message": f"Operation {idx + 1}: Transfer requires 'to_category' field.", "status": "error", "category": from_cat}
    if from_cat == to_cat:
        return {"message": f"Operation {idx + 1}: Cannot transfer to the same category.", "status": "error", "category": from_cat}
    if transfer_amount is None:
        return {"message": f"Operation {idx + 1}: Transfer requires 'transfer_amount' field.", "status": "error", "category": from_cat}
    if not isinstance(transfer_amount, (int, float)):
        return {"message": f"Operation {idx + 1}: 'transfer_amount' must be a number.", "status": "error", "category": from_cat}
    if transfer_amount <= 0:
        return {
            "message": (
                f"Operation {idx + 1}: 'transfer_amount' must be positive. "
                f"Got {transfer_amount}. Use a positive value - sign handling is automatic."
            ),
            "status": "error",
            "category": from_cat,
        }
    return None


def mutate_categories_handler(
    operations: List[Dict[str, Any]],
    user_id: Optional[str] = None,
    bank_name: Optional[str] = None,
    month_year: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Mutate category totals through edit or transfer operations.

    Args:
        operations: List of operation dicts. Each operation must have one of these types:
        
            EDIT operation - set absolute amount:
            - type: 'edit'
            - category: Category name (required)
            - new_amount: New total amount for category (required)
            - note: Optional note/description
            
            TRANSFER operation - move amount between categories (zero-sum):
            - type: 'transfer'
            - from_category: Source category name (required)
            - to_category: Destination category name (required)
            - transfer_amount: Positive amount to move (required)
            - note: Optional note/description
            
            Sign handling for transfers is AUTOMATIC:
            - If source is expense (negative): source gets less negative, dest gets more negative
            - If source is income (positive): source gets less positive, dest gets more positive
            - Net change is always 0 (preserves statement reconciliation)
            
        user_id: Optional user ID (defaults to test user)
        bank_name: Optional filter by bank name
        month_year: Optional filter by specific month (YYYY-MM)

    Returns:
        Dict with:
        - updated_categories: Dict of category names to their new amounts (only affected categories)
        - change_summary: Array of operation results with status messages
    """
    started_at = logger.tool_call_start(
        "mutate_categories",
        {
            "user_id": user_id,
            "bank_name": bank_name,
            "month_year": month_year,
            "operation_count": len(operations),
        },
    )

    db = SessionLocal()
    try:
        resolved_user_id = resolve_user_id(user_id)

        # Validate operations
        change_summary: List[Dict[str, Any]] = []

        for idx, op in enumerate(operations):
            op_type = op.get("type")

            if op_type not in ("edit", "transfer"):
                change_summary.append({
                    "message": (
                        f"Operation {idx + 1}: Invalid type '{op_type}'. "
                        "Supported types: 'edit' (set absolute amount), "
                        "'transfer' (move amount between categories, zero-sum)."
                    ),
                    "status": "error",
                    "category": "unknown",
                })
                continue

            if op_type == "edit":
                error = _validate_edit_op(op, idx)
            else:
                error = _validate_transfer_op(op, idx)

            if error:
                change_summary.append(error)

        # If any operations failed validation, return early
        if any(change["status"] == "error" for change in change_summary):
            logger.warn("Operations failed validation", {
                "failed_count": sum(1 for c in change_summary if c["status"] == "error"),
            })
            return {
                "updated_categories": {},
                "change_summary": change_summary,
                "status": "error",
            }

        # Fetch current transactions (canonical source)
        query = db.query(Transaction).filter(
            Transaction.user_id == resolved_user_id
        )

        if bank_name:
            query = query.filter(Transaction.bank_name == bank_name)
        if month_year:
            date_from, date_to = month_year_to_date_range(month_year)
            query = query.filter(Transaction.date >= date_from, Transaction.date <= date_to)

        transactions = query.all()
        if not transactions:
            logger.warn("No transactions found for mutation scope", {
                "user_id": resolved_user_id,
                "bank_name": bank_name,
                "month_year": month_year,
            })
            return {
                "updated_categories": {},
                "change_summary": [{
                    "message": "No transactions found for the specified scope.",
                    "status": "error",
                    "category": "unknown",
                }],
                "status": "error",
            }

        scope_banks = {tx.bank_name for tx in transactions}
        scope_months = {tx.date.strftime("%Y-%m") for tx in transactions}
        if not bank_name and len(scope_banks) > 1:
            return {
                "updated_categories": {},
                "change_summary": [{
                    "message": (
                        "Multiple banks found for the specified scope. "
                        "Provide bank_name to target a single bank."
                    ),
                    "status": "error",
                    "category": "unknown",
                }],
                "status": "error",
            }
        if not month_year and len(scope_months) > 1:
            return {
                "updated_categories": {},
                "change_summary": [{
                    "message": (
                        "Multiple months found for the specified scope. "
                        "Provide month_year to target a single month."
                    ),
                    "status": "error",
                    "category": "unknown",
                }],
                "status": "error",
            }
        currency = transactions[0].currency
        default_bank = bank_name or transactions[0].bank_name
        scope_month = month_year or (next(iter(scope_months)) if len(scope_months) == 1 else None)

        category_totals: Dict[str, Decimal] = {}
        for tx in transactions:
            category_totals[tx.category] = category_totals.get(tx.category, Decimal("0")) + Decimal(str(tx.amount))

        def adjustment_date() -> date:
            if scope_month:
                _, last_day = month_year_to_date_range(scope_month)
                return last_day
            return date.today()

        # Apply operations by inserting adjustment transactions
        try:
            for op in operations:
                op_type = op["type"]

                if op_type == "edit":
                    category = op["category"]
                    new_amount = Decimal(str(op["new_amount"]))
                    current = category_totals.get(category, Decimal("0"))
                    delta = new_amount - current
                    if delta == 0:
                        continue

                    adj_tx = Transaction(
                        user_id=resolved_user_id,
                        date=adjustment_date(),
                        description=f"Adjustment edit: {category}",
                        merchant="Adjustment",
                        amount=delta,
                        currency=currency,
                        category=category,
                        bank_name=default_bank,
                        profile=None,
                    )
                    db.add(adj_tx)
                    category_totals[category] = new_amount
                    change_summary.append({
                        "message": f"Adjusted category '{category}': {current} → {new_amount}.",
                        "status": "success",
                        "category": category,
                        "details": {
                            "category": category,
                            "old_amount": float(current),
                            "new_amount": float(new_amount),
                        },
                    })

                elif op_type == "transfer":
                    from_cat = op["from_category"]
                    to_cat = op["to_category"]
                    transfer_amount = Decimal(str(op["transfer_amount"]))
                    note = op.get("note", "")

                    if from_cat not in category_totals:
                        change_summary.append({
                            "message": f"Source category '{from_cat}' not found.",
                            "status": "error",
                            "category": from_cat,
                        })
                        continue

                    from_current = category_totals.get(from_cat, Decimal("0"))
                    to_current = category_totals.get(to_cat, Decimal("0"))
                    is_expense = from_current < 0

                    if is_expense:
                        from_delta = transfer_amount
                        to_delta = -transfer_amount
                        sign_explanation = (
                            f"expense transfer: {from_cat} +{transfer_amount} (less negative), "
                            f"{to_cat} -{transfer_amount} (more negative)"
                        )
                    else:
                        from_delta = -transfer_amount
                        to_delta = transfer_amount
                        sign_explanation = (
                            f"income transfer: {from_cat} -{transfer_amount} (less positive), "
                            f"{to_cat} +{transfer_amount} (more positive)"
                        )

                    from_new = from_current + from_delta
                    to_new = to_current + to_delta

                    adj_from = Transaction(
                        user_id=resolved_user_id,
                        date=adjustment_date(),
                        description=f"Adjustment transfer from {from_cat} to {to_cat}. {note}".strip(),
                        merchant="Adjustment",
                        amount=from_delta,
                        currency=currency,
                        category=from_cat,
                        bank_name=default_bank,
                        profile=None,
                    )
                    adj_to = Transaction(
                        user_id=resolved_user_id,
                        date=adjustment_date(),
                        description=f"Adjustment transfer from {from_cat} to {to_cat}. {note}".strip(),
                        merchant="Adjustment",
                        amount=to_delta,
                        currency=currency,
                        category=to_cat,
                        bank_name=default_bank,
                        profile=None,
                    )
                    db.add(adj_from)
                    db.add(adj_to)
                    category_totals[from_cat] = from_new
                    category_totals[to_cat] = to_new

                    change_summary.append({
                        "message": (
                            f"Transferred {transfer_amount} from '{from_cat}' to '{to_cat}'. "
                            f"{from_cat}: {from_current} → {from_new}, "
                            f"{to_cat}: {to_current} → {to_new}. "
                            f"Net change: 0. ({sign_explanation})"
                        ),
                        "status": "success",
                        "category": f"{from_cat} → {to_cat}",
                        "details": {
                            "from_category": from_cat,
                            "to_category": to_cat,
                            "transfer_amount": float(transfer_amount),
                            "from_old": float(from_current),
                            "from_new": float(from_new),
                            "to_old": float(to_current),
                            "to_new": float(to_new),
                            "net_change": 0,
                        },
                    })

            db.commit()
            logger.info("Category mutations applied successfully", {
                "operation_count": len(operations),
                "success_count": sum(1 for c in change_summary if c["status"] == "success"),
            })

        except Exception as e:
            db.rollback()
            logger.tool_call_error(
                "mutate_categories",
                started_at,
                e,
                ErrorType.DB_ERROR,
            )
            change_summary.append({
                "message": f"Database error: {str(e)}",
                "status": "error",
                "category": "unknown",
            })
            raise
        
        # Extract updated categories from change_summary (lean response)
        updated_categories: Dict[str, float] = {}
        for change in change_summary:
            if change.get("status") == "success":
                details = change.get("details", {})
                if "from_category" in details:
                    # Transfer operation - has from/to details
                    updated_categories[details["from_category"]] = details["from_new"]
                    updated_categories[details["to_category"]] = details["to_new"]
                elif "category" in details and "new_amount" in details:
                    # Edit operation - has category/new_amount
                    updated_categories[details["category"]] = details["new_amount"]
        
        logger.tool_call_end("mutate_categories", started_at, {
            "operation_count": len(operations),
            "success_count": sum(1 for c in change_summary if c["status"] == "success"),
        })
        
        return {
            "updated_categories": updated_categories,
            "change_summary": change_summary,
            "status": "success" if any(c["status"] == "success" for c in change_summary) else "error",
        }
        
    except Exception as e:
        logger.tool_call_error(
            "mutate_categories",
            started_at,
            e,
            ErrorType.UNKNOWN_ERROR,
        )
        raise
    
    finally:
        db.close()
