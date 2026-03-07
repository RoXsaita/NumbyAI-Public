"""
UI Dashboard Tool - Category Summary Pivot Table Provider

This module provides category summary data in pivot table format for the dashboard widget.
It aggregates Transaction records and creates a pivot view with categories as rows and months as columns.

The widget receives raw pivot data and decides how to visualize it.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Optional, List

from sqlalchemy import func

from app.database import SessionLocal, Budget, CategorizationPreference, Transaction, resolve_user_id
from app.tools.category_helpers import MANUAL_REVIEW
from datetime import date
from app.logger import classify_error, create_logger
from app.schemas.dashboard import (
    CoverageWindow,
    DashboardProps,
    InitialFilters,
    Metrics,
    PivotTable,
    SegmentMetric,
    Statement,
    TopVariance,
    CategorySummaryData,
    UserSettings,
)
from app.utils import decimal_to_float, month_year_expr, month_year_to_date_range

# Create logger for this module
logger = create_logger("financial_data")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


class SummaryLike:
    def __init__(
        self,
        summary_id: int,
        bank_name: str,
        month_year: str,
        category: str,
        amount: Decimal,
        currency: str,
        transaction_count: int,
        profile: Optional[str],
    ) -> None:
        self.id = summary_id
        self.bank_name = bank_name
        self.month_year = month_year
        self.category = category
        self.amount = amount
        self.currency = currency
        self.transaction_count = transaction_count
        self.profile = profile
        self.insights = None


def _month_year_expr():
    return month_year_expr()


def _fetch_transaction_summaries(
    db: SessionLocal,
    user_id: str,
    bank_name: Optional[str] = None,
    month_year: Optional[str] = None,
    categories: Optional[List[str]] = None,
    profile: Optional[str] = None,
) -> tuple[List[SummaryLike], set[str], set[str], set[str]]:
    """Fetch grouped transaction summaries without loading every row into memory."""
    month_expr = _month_year_expr()
    query = (
        db.query(
            Transaction.bank_name.label("bank_name"),
            month_expr.label("month_year"),
            Transaction.category.label("category"),
            Transaction.profile.label("profile"),
            Transaction.currency.label("currency"),
            func.sum(Transaction.amount).label("amount"),
            func.count(Transaction.id).label("transaction_count"),
        )
        .filter(Transaction.user_id == user_id)
        .filter(Transaction.category != MANUAL_REVIEW)
    )

    if bank_name:
        query = query.filter(Transaction.bank_name == bank_name)
    if month_year:
        date_from, date_to = month_year_to_date_range(month_year)
        query = query.filter(Transaction.date >= date_from, Transaction.date <= date_to)
    if categories:
        query = query.filter(Transaction.category.in_(categories))
    if profile:
        query = query.filter(Transaction.profile == profile)

    query = query.group_by(
        Transaction.bank_name,
        month_expr,
        Transaction.category,
        Transaction.profile,
        Transaction.currency,
    )

    rows = query.all()
    summaries: List[SummaryLike] = []
    months: set[str] = set()
    banks: set[str] = set()
    profiles: set[str] = set()

    for idx, row in enumerate(rows, start=1):
        month_value = row.month_year
        bank_value = row.bank_name
        category_value = row.category
        currency_value = row.currency or "USD"
        amount_value = row.amount if row.amount is not None else Decimal("0")
        count_value = int(row.transaction_count or 0)
        profile_value = row.profile

        if month_value:
            months.add(month_value)
        if bank_value:
            banks.add(bank_value)
        if profile_value:
            profiles.add(profile_value)

        summaries.append(
            SummaryLike(
                idx,
                bank_value,
                month_value,
                category_value,
                amount_value,
                currency_value,
                count_value,
                profile_value,
            )
        )

    return summaries, months, banks, profiles


# ============================================================================
# DATA AGGREGATION
# ============================================================================

INTERNAL_TRANSFER_KEYWORDS = (
    "transfer",
    "transfers",
    "cash",
    "savings",
)


def _get_budget_for_category(
    budget_lookup: Dict[str, Dict[str, float]],
    category: str,
    month: str,
) -> float:
    """
    Get budget for a category/month, falling back to default budget.
    
    Args:
        budget_lookup: Dict of {category: {month_year: amount, None: default_amount}}
        category: Category name
        month: Month in YYYY-MM format
    
    Returns:
        Budget amount (0.0 if no budget set)
    """
    if category not in budget_lookup:
        return 0.0
    cat_budgets = budget_lookup[category]
    # Try month-specific first, then default (None key)
    if month in cat_budgets:
        return cat_budgets[month]
    if None in cat_budgets:
        return cat_budgets[None]
    return 0.0


def _classify_category(name: str, total_amount: float) -> str:
    """Return inflows, outflows, or internal transfers classification."""
    lower = name.lower()
    if any(keyword in lower for keyword in INTERNAL_TRANSFER_KEYWORDS):
        return "internal_transfers"
    if total_amount >= 0:
        return "inflows"
    return "outflows"


def _build_empty_dashboard(
    available_banks: Optional[List[str]],
    available_months: Optional[List[str]],
    available_profiles: Optional[List[str]],
    coverage: CoverageWindow,
    initial_filters: Optional[InitialFilters],
    user_settings: Optional[UserSettings],
    *,
    default_currency: str = "USD",
    statement_insights: Optional[str] = None,
) -> DashboardProps:
    """Return DashboardProps for the empty-summaries case."""
    empty_pivot = PivotTable(
        categories=[],
        months=[],
        actuals=[],
        budgets=[],
        transaction_counts=[],
        category_totals={},
        category_budget_totals={},
        month_totals={},
        month_budget_totals={},
        category_shares={},
        currency=default_currency,
    )

    empty_metrics = Metrics(
        inflows=0.0,
        outflows=0.0,
        internal_transfers=0.0,
        net_cash=0.0,
        budget_coverage_pct=0.0,
        latest_month=None,
        previous_month=None,
        month_over_month_delta=None,
        month_over_month_pct=None,
        segments=[],
        top_variances=[],
    )

    empty_statement = Statement(
        id="empty_dashboard",
        month="No data",
        bank=None,
        currency=default_currency,
    )

    return DashboardProps.create(
        statement=empty_statement,
        transactions=[],
        metrics=empty_metrics,
        pivot=empty_pivot,
        currency=default_currency,
        banks=available_banks or [],
        coverage=coverage,
        initial_filters=initial_filters,
        statement_insights=statement_insights,
        category_summaries=[],
        available_months=available_months or [],
        available_banks=available_banks or [],
        available_profiles=available_profiles or [],
        user_settings=user_settings,
    )


def _build_variance_records(
    sorted_categories: List[str],
    category_totals: Dict[str, float],
    budget_lookup: Optional[Dict[str, Dict[str, float]]],
    months: List[str],
    classification_map: Dict[str, str],
) -> List[TopVariance]:
    """Build list of variance records (actual vs budget) for non-internal-transfer categories."""
    variance_records: List[TopVariance] = []
    for category in sorted_categories:
        classification = classification_map[category]
        if classification == "internal_transfers":
            continue
        actual_total = category_totals[category]
        budget_total = (
            round(
                sum(
                    _get_budget_for_category(budget_lookup, category, month)
                    for month in months
                ),
                2,
            )
            if budget_lookup
            else 0.0
        )
        if classification == "outflows":
            actual_abs = abs(actual_total)
            budget_abs = abs(budget_total)
            variance_value = round(actual_abs - budget_abs, 2)
            variance_pct = round(
                (variance_value / budget_abs * 100), 2
            ) if budget_abs else 0.0
            direction = "over" if actual_abs > budget_abs else "under"
        else:
            variance_value = round(actual_total - budget_total, 2)
            budget_abs = abs(budget_total)
            variance_pct = round(
                (variance_value / budget_abs * 100), 2
            ) if budget_abs else 0.0
            direction = "over" if actual_total > budget_total else "under"
        variance_records.append(
            TopVariance(
                category=category,
                actual=round(actual_total, 2),
                budget=round(budget_total, 2),
                variance=variance_value,
                variance_pct=variance_pct,
                direction=direction,
            )
        )
    return variance_records


def _build_dashboard_props(
    summaries: list[SummaryLike],
    bank_name: Optional[str],
    month_filter: Optional[str],
    initial_filters: Optional[InitialFilters] = None,
    statement_insights: Optional[str] = None,
    budget_lookup: Optional[Dict[str, Dict[str, float]]] = None,
    available_months: Optional[List[str]] = None,
    available_banks: Optional[List[str]] = None,
    available_profiles: Optional[List[str]] = None,
    default_currency: str = "USD",
    user_settings: Optional[UserSettings] = None,
    coverage_start: Optional[str] = None,
    coverage_end: Optional[str] = None,
) -> DashboardProps:
    """Create the full dashboard payload from raw summaries."""
    # Handle empty summaries - return empty dashboard instead of raising error
    if not summaries:
        empty_coverage = CoverageWindow(
            start=coverage_start,
            end=coverage_end,
        )
        return _build_empty_dashboard(
            available_banks,
            available_months,
            available_profiles,
            empty_coverage,
            initial_filters,
            user_settings,
            default_currency=default_currency,
            statement_insights=statement_insights,
        )

    pivot_data: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pivot_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_months = set()
    actual_months = set()  # Months with actual transaction data (not budget-only)
    all_categories = set()
    banks = set()
    currency = summaries[0].currency or "USD"

    category_summaries: List[CategorySummaryData] = []

    for summary in summaries:
        category = summary.category
        month = summary.month_year
        amount = decimal_to_float(summary.amount)
        count = int(summary.transaction_count)

        pivot_data[category][month] += amount
        pivot_counts[category][month] += count
        all_months.add(month)
        actual_months.add(month)  # Track months with actual data
        all_categories.add(category)
        banks.add(summary.bank_name)

        category_summaries.append(
            CategorySummaryData(
                category=category,
                month=month,
                bank=summary.bank_name,
                amount=amount,
                count=count,
                profile=summary.profile,
                insights=summary.insights,
            )
        )

    # Include months that have budget data but no actual summaries
    # This ensures budget-only months appear in the dashboard
    # NOTE: These are NOT added to actual_months to avoid affecting latest_month calculation
    if budget_lookup:
        for category, month_budgets in budget_lookup.items():
            # Include category if it has any budget data (default or month-specific)
            all_categories.add(category)
            for month_year in month_budgets.keys():
                # Only add specific months to all_months (skip None/default budgets)
                if month_year is not None:
                    all_months.add(month_year)

    sorted_months = sorted(all_months)
    sorted_banks = sorted(banks)

    raw_rows: Dict[str, Dict[str, Any]] = {}
    month_totals = {month: 0.0 for month in sorted_months}
    month_budget_totals = {month: 0.0 for month in sorted_months}

    for category in all_categories:
        row_data: List[float] = []
        row_counts: List[int] = []
        for month in sorted_months:
            amount = round(pivot_data[category].get(month, 0.0), 2)
            count = pivot_counts[category].get(month, 0)
            row_data.append(amount)
            row_counts.append(count)

        total_amount = round(sum(row_data), 2)
        # Get budget for each month from budget_lookup, or use 0 if not set
        row_budget = []
        for month in sorted_months:
            if budget_lookup:
                budget_val = _get_budget_for_category(budget_lookup, category, month)
            else:
                budget_val = 0.0
            row_budget.append(round(budget_val, 2))
        budget_total = round(sum(row_budget), 2)

        for idx, month in enumerate(sorted_months):
            month_totals[month] += row_data[idx]
            month_budget_totals[month] += row_budget[idx]

        raw_rows[category] = {
            "actuals": row_data,
            "counts": row_counts,
            "budget": row_budget,
            "total": total_amount,
            "budget_total": budget_total,
        }

    sorted_categories = sorted(
        raw_rows.keys(),
        key=lambda key: abs(raw_rows[key]["total"]),
        reverse=True,
    )

    data_matrix = []
    budget_matrix = []
    counts_matrix = []
    category_totals: Dict[str, float] = {}
    category_budget_totals: Dict[str, float] = {}

    for category in sorted_categories:
        row = raw_rows[category]
        data_matrix.append(row["actuals"])
        budget_matrix.append(row["budget"])
        counts_matrix.append(row["counts"])
        category_totals[category] = row["total"]
        category_budget_totals[category] = row["budget_total"]

    classification_map = {
        cat: _classify_category(cat, category_totals[cat])
        for cat in sorted_categories
    }

    expense_total_abs = sum(
        abs(category_totals[cat])
        for cat in sorted_categories
        if category_totals[cat] < 0 and classification_map[cat] == "outflows"
    )
    category_shares = {
        cat: round(
            (abs(category_totals[cat]) / expense_total_abs * 100), 2
        ) if expense_total_abs and category_totals[cat] < 0 and classification_map[cat] == "outflows" else 0.0
        for cat in sorted_categories
    }

    segment_actual_totals = {
        "inflows": sum(
            category_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "inflows"
        ),
        "outflows": sum(
            category_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "outflows"
        ),
        "internal_transfers": sum(
            category_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "internal_transfers"
        ),
    }
    segment_budget_totals = {
        "inflows": sum(
            category_budget_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "inflows"
        ),
        "outflows": sum(
            category_budget_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "outflows"
        ),
        "internal_transfers": sum(
            category_budget_totals[cat]
            for cat in sorted_categories
            if classification_map[cat] == "internal_transfers"
        ),
    }

    def _segment_metric(name: str) -> SegmentMetric:
        actual_signed = segment_actual_totals.get(name, 0.0)
        budget_signed = segment_budget_totals.get(name, 0.0)
        actual = abs(actual_signed)
        budget = abs(budget_signed)
        variance = actual - budget
        variance_pct = round((variance / budget * 100), 2) if budget else 0.0
        return SegmentMetric(
            name=name,
            actual=round(actual, 2),
            budget=round(budget, 2),
            variance=round(variance, 2),
            variance_pct=variance_pct,
        )

    segments = [_segment_metric(name) for name in ("inflows", "outflows", "internal_transfers")]

    inflows = round(max(segment_actual_totals["inflows"], 0.0), 2)
    outflows = round(abs(segment_actual_totals["outflows"]), 2)
    internal_transfers = round(abs(segment_actual_totals["internal_transfers"]), 2)
    net_cash = round(
        segment_actual_totals["inflows"]
        + segment_actual_totals["outflows"]
        + segment_actual_totals["internal_transfers"],
        2,
    )

    # Use actual_months (months with real transactions) for latest/previous month calculation
    # This avoids picking budget-only months as the "latest" month
    sorted_actual_months = sorted(actual_months)
    latest_month = sorted_actual_months[-1] if sorted_actual_months else None
    previous_month = sorted_actual_months[-2] if len(sorted_actual_months) > 1 else None
    month_over_month_delta = None
    month_over_month_pct = None
    if latest_month and previous_month:
        latest_value = month_totals[latest_month]
        previous_value = month_totals[previous_month]
        month_over_month_delta = round(latest_value - previous_value, 2)
        if previous_value:
            month_over_month_pct = round(
                month_over_month_delta / abs(previous_value) * 100,
                2,
            )

    expense_budget_abs = abs(segment_budget_totals.get("outflows", 0.0))
    budget_coverage_pct = (
        round(outflows / expense_budget_abs * 100, 2)
        if expense_budget_abs
        else 0.0
    )

    variance_records = _build_variance_records(
        sorted_categories,
        category_totals,
        budget_lookup,
        sorted_months,
        classification_map,
    )

    top_variances = sorted(
        variance_records,
        key=lambda var: abs(var.variance),
        reverse=True,
    )[:5]

    pivot_table = PivotTable(
        categories=sorted_categories,
        months=sorted_months,
        actuals=data_matrix,
        budgets=budget_matrix,
        transaction_counts=counts_matrix,
        category_totals={
            cat: round(category_totals[cat], 2) for cat in sorted_categories
        },
        category_budget_totals={
            cat: round(category_budget_totals[cat], 2) for cat in sorted_categories
        },
        month_totals={month: round(month_totals[month], 2) for month in sorted_months},
        month_budget_totals={
            month: round(month_budget_totals[month], 2) for month in sorted_months
        },
        category_shares=category_shares,
        currency=currency,
    )

    metrics = Metrics(
        inflows=inflows,
        outflows=outflows,
        internal_transfers=internal_transfers,
        net_cash=net_cash,
        budget_coverage_pct=budget_coverage_pct,
        latest_month=latest_month,
        previous_month=previous_month,
        month_over_month_delta=month_over_month_delta,
        month_over_month_pct=month_over_month_pct,
        segments=segments,
        top_variances=top_variances,
    )

    statement_month = (
        month_filter
        if month_filter
        else (latest_month if len(sorted_months) == 1 else "Multi-period")
    )
    summary_id = getattr(summaries[0], "id", "no_id")
    statement = Statement(
        id=f"pivot_{summary_id}",
        month=statement_month or "Multi-period",
        bank=bank_name or (sorted_banks[0] if sorted_banks else None),
        currency=currency,
    )

    coverage = CoverageWindow(
        start=coverage_start,
        end=coverage_end,
    )

    return DashboardProps.create(
        statement=statement,
        transactions=[],
        metrics=metrics,
        pivot=pivot_table,
        currency=currency,
        banks=list(sorted_banks),
        coverage=coverage,
        initial_filters=initial_filters,
        statement_insights=statement_insights,
        category_summaries=category_summaries,
        available_months=available_months or list(sorted_months),
        available_banks=available_banks or list(sorted_banks),
        available_profiles=available_profiles or [],
        user_settings=user_settings,
    )

# ============================================================================
# MAIN HANDLER
# ============================================================================

def get_financial_data_handler(
    user_id: Optional[str] = None,
    bank_name: Optional[str] = None,
    month_year: Optional[str] = None,
    categories: Optional[List[str]] = None,
    profile: Optional[str] = None,
    tab: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build dashboard data from transactions for the web app.

    Args:
        user_id: Optional user ID (defaults to test user)
        bank_name: Optional filter by bank name
        month_year: Optional filter by specific month (YYYY-MM)
        categories: Optional list of categories to include
        profile: Optional household profile filter (e.g., "Me", "Partner", "Joint")
        tab: Optional tab to show (if "overview", defaults to "journey")

    Returns:
        Dashboard payload as a dict.
    """
    # Normalize profile
    if profile:
        profile = profile.strip()
        if not profile:
            profile = None

    # Handle tab parameter: if "overview" is specified, default to "journey"
    if tab and tab.strip().lower() == "overview":
        tab = "journey"
    
    # Log tool call start
    started_at = logger.tool_call_start(
        "get_financial_data",
        {"user_id": user_id, "bank_name": bank_name, "month_year": month_year, "categories": categories, "profile": profile},
    )

    db = SessionLocal()
    try:
        resolved_user_id = resolve_user_id(user_id)

        logger.debug("Fetching category summaries from database", {
            "user_id": resolved_user_id,
            "bank_name": bank_name,
            "month_year": month_year,
            "categories": categories,
            "profile": profile,
        })

        all_summaries, all_months, all_banks, all_profiles = _fetch_transaction_summaries(
            db,
            resolved_user_id,
        )

        if all_summaries:
            logger.info("Using Transaction table for aggregation", {
                "summary_count": len(all_summaries)
            })
        else:
            logger.info("No transactions found for user", {"user_id": resolved_user_id})

        available_profiles = all_profiles

        # Fetch user budgets
        budget_query = db.query(Budget).filter(Budget.user_id == resolved_user_id)
        all_budgets = budget_query.all()
        
        # Build budget lookup: {category: {month_year: amount, None: default}}
        budget_lookup: Dict[str, Dict[str, float]] = {}
        for b in all_budgets:
            if b.category not in budget_lookup:
                budget_lookup[b.category] = {}
            # month_year can be None (default budget) or specific month
            key = b.month_year  # None for default, "YYYY-MM" for specific
            budget_lookup[b.category][key] = decimal_to_float(b.amount)
        
        # Fetch user's functional currency from settings (for empty dashboard)
        # Also fetch actual user settings for progression tracking (without defaults)
        default_currency = "USD"  # Default fallback
        user_settings = None
        settings_pref = (
            db.query(CategorizationPreference)
            .filter(
                CategorizationPreference.user_id == resolved_user_id,
                CategorizationPreference.preference_type == "settings",
                CategorizationPreference.name == "user_settings",
                CategorizationPreference.enabled.is_(True)
            )
            .first()
        )
        if settings_pref and settings_pref.rule:
            settings_dict = settings_pref.rule
            # Get currency for display (with default)
            default_currency = settings_dict.get("functional_currency", "USD")
            
            # Build user_settings object - only include fields that are actually set (not defaulted)
            user_settings_dict = {}
            if "functional_currency" in settings_dict:
                user_settings_dict["functional_currency"] = settings_dict["functional_currency"]
            if "bank_accounts_count" in settings_dict:
                user_settings_dict["bank_accounts_count"] = settings_dict["bank_accounts_count"]
            if "registered_banks" in settings_dict:
                user_settings_dict["registered_banks"] = settings_dict["registered_banks"]
            if "profiles" in settings_dict:
                user_settings_dict["profiles"] = settings_dict["profiles"]
            if "onboarding_complete" in settings_dict:
                user_settings_dict["onboarding_complete"] = settings_dict["onboarding_complete"]
            
            # Only create UserSettings object if we have at least one field
            if user_settings_dict:
                user_settings = UserSettings(**user_settings_dict)

        # Collect available months and banks from ALL summaries (for widget dropdowns)
        available_months_set = set(all_months)
        available_banks_set = set(all_banks)
        
        # Also include months that have budget data
        for category, month_budgets in budget_lookup.items():
            for m in month_budgets.keys():
                if m is not None:
                    available_months_set.add(m)
        
        available_months = sorted(available_months_set)
        available_banks = sorted(available_banks_set)

        # Prepare initial filters
        # Always set initial_filters to include default_tab
        # Default to 'journey' tab when no parameters are provided or if tab is "overview"
        default_tab_value = None
        if not (bank_name or month_year or categories or profile) and not tab:
            # No filters and no tab specified: default to journey
            default_tab_value = 'journey'
        elif tab:
            # Tab explicitly specified: use it (already handled "overview" -> "journey" above)
            default_tab_value = tab.strip().lower() if tab else None
        
        initial_filters = InitialFilters(
            bank_name=bank_name if bank_name else None,
            month_year=month_year if month_year else None,
            profile=profile if profile else None,
            default_tab=default_tab_value,
        )
        coverage_start, coverage_end = db.query(
            func.min(Transaction.date),
            func.max(Transaction.date),
        ).filter(Transaction.user_id == resolved_user_id).one()

        coverage_start_str = coverage_start.isoformat() if coverage_start else None
        coverage_end_str = coverage_end.isoformat() if coverage_end else None

        dashboard_props = _build_dashboard_props(
            all_summaries,
            bank_name=None,
            month_filter=None,
            initial_filters=initial_filters,
            statement_insights=None,
            budget_lookup=budget_lookup if all_summaries else None,
            available_months=available_months,
            available_banks=available_banks,
            available_profiles=sorted(list(available_profiles)),
            default_currency=default_currency,
            user_settings=user_settings,
            coverage_start=coverage_start_str,
            coverage_end=coverage_end_str,
        )

        payload = dashboard_props.model_dump()
        payload["summary_count"] = len(all_summaries)

        logger.tool_call_end(
            "get_financial_data",
            started_at,
            {
                "summary_count": len(all_summaries),
                "months": len(dashboard_props.pivot.months),
            },
        )

        return payload

    except Exception as e:
        # Log error
        logger.tool_call_error(
            "get_financial_data",
            started_at,
            e,
            classify_error(e),
        )
        raise

    finally:
        db.close()
