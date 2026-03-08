"""
Currency conversion service using the Frankfurter API (ECB data).

Fetches average monthly exchange rates (average of first and last business day)
and caches them in-memory + DB for persistence across restarts.

API docs: https://frankfurter.dev/
"""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple

import requests

from app.logger import create_logger

logger = create_logger("currency_service")

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"
REQUEST_TIMEOUT_SECONDS = 10

_rate_cache: Dict[Tuple[str, str, str], Decimal] = {}


def _fetch_rate_for_date(
    target_date: str,
    base_currency: str,
    target_currency: str,
) -> Optional[Decimal]:
    """Fetch a single exchange rate from Frankfurter for a specific date.

    The API snaps to the nearest prior business day if the date falls on a
    weekend or holiday, so callers don't need to worry about that.
    """
    url = f"{FRANKFURTER_BASE_URL}/{target_date}"
    params = {"base": base_currency, "symbols": target_currency}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        rate_value = data.get("rates", {}).get(target_currency)
        if rate_value is None:
            logger.warn("Rate not found in API response", {
                "date": target_date,
                "base": base_currency,
                "target": target_currency,
                "response_keys": list(data.get("rates", {}).keys()),
            })
            return None
        return Decimal(str(rate_value))
    except requests.RequestException as exc:
        logger.warn("Frankfurter API request failed", {
            "date": target_date,
            "base": base_currency,
            "target": target_currency,
            "error": str(exc),
        })
        return None


def get_monthly_average_rate(
    year_month: str,
    from_currency: str,
    to_currency: str,
) -> Optional[Decimal]:
    """Return the average exchange rate for a month (first + last business day / 2).

    Args:
        year_month: Month in "YYYY-MM" format.
        from_currency: ISO 4217 code of the statement (source) currency.
        to_currency: ISO 4217 code of the functional (target) currency.

    Returns:
        Average rate as Decimal, or None if the API is unreachable.
    """
    if from_currency == to_currency:
        return Decimal("1")

    cache_key = (year_month, from_currency, to_currency)
    if cache_key in _rate_cache:
        return _rate_cache[cache_key]

    try:
        year, month = int(year_month[:4]), int(year_month[5:7])
    except (ValueError, IndexError):
        logger.error("Invalid year_month format", {"year_month": year_month})
        return None

    first_day = date(year, month, 1).isoformat()
    last_day_num = calendar.monthrange(year, month)[1]
    last_day = date(year, month, last_day_num).isoformat()

    rate_start = _fetch_rate_for_date(first_day, from_currency, to_currency)
    rate_end = _fetch_rate_for_date(last_day, from_currency, to_currency)

    if rate_start is not None and rate_end is not None:
        avg = ((rate_start + rate_end) / 2).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    elif rate_start is not None:
        avg = rate_start
    elif rate_end is not None:
        avg = rate_end
    else:
        logger.warn("Could not fetch any rate for month", {
            "year_month": year_month,
            "from": from_currency,
            "to": to_currency,
        })
        return None

    _rate_cache[cache_key] = avg
    logger.info("Fetched monthly average rate", {
        "year_month": year_month,
        "from": from_currency,
        "to": to_currency,
        "rate_start": str(rate_start),
        "rate_end": str(rate_end),
        "average": str(avg),
    })
    return avg


def prefetch_rates_for_months(
    months: list[str],
    from_currency: str,
    to_currency: str,
) -> Dict[str, Optional[Decimal]]:
    """Prefetch rates for multiple months at once. Returns {year_month: rate}.

    Useful for batch operations where we know all months upfront.
    """
    if from_currency == to_currency:
        return {m: Decimal("1") for m in months}

    results: Dict[str, Optional[Decimal]] = {}
    for month in sorted(set(months)):
        results[month] = get_monthly_average_rate(month, from_currency, to_currency)
    return results


def convert_amount(
    amount: Decimal,
    rate: Decimal,
) -> Decimal:
    """Convert an amount using the given exchange rate, rounded to 2 decimal places."""
    return (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clear_cache() -> None:
    """Clear the in-memory rate cache (useful for testing)."""
    _rate_cache.clear()
