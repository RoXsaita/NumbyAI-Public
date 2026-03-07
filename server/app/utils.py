"""Shared utility functions used across the app."""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from sqlalchemy import func

from app.config import settings
from app.logger import Logger


def decimal_to_float(value: Decimal | float | int | None) -> float:
    """Convert Decimal to float for JSON serialization."""
    if value is None:
        return 0.0
    return float(value)


def month_year_expr():
    """SQL expression to normalize transaction dates into YYYY-MM buckets."""
    from app.database import Transaction

    if settings.database_url.startswith("sqlite"):
        return func.strftime("%Y-%m", Transaction.date)
    return func.to_char(Transaction.date, "YYYY-MM")


def month_year_to_date_range(month_year: str) -> tuple[date, date]:
    """Convert a YYYY-MM string into (first_day, last_day) date range."""
    year, month = map(int, month_year.split("-"))
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def safe_emit_progress(
    callback: Optional[Callable[[Dict[str, Any]], None]],
    payload: Dict[str, Any],
    logger: Logger,
) -> None:
    """Invoke a progress callback, swallowing exceptions."""
    if not callback:
        return
    try:
        callback(payload)
    except Exception as e:
        logger.warn("Progress callback failed", {"error": str(e)})
