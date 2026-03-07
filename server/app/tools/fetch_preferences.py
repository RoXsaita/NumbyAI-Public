"""Unified helper to fetch user preferences (settings, parsing, categorization)."""
from typing import Optional, List, Dict, Any, Literal, Union

from sqlalchemy import func

from app.database import (
    CategorizationPreference,
    Budget,
    SessionLocal,
    Transaction,
    resolve_user_id,
)
from app.logger import classify_error, create_logger
from app.utils import month_year_expr

logger = create_logger("fetch_preferences")

PreferenceType = Literal["categorization", "parsing", "settings", "list"]

SETTINGS_PREFERENCE_NAME = "user_settings"


def _month_year_expr():
    """SQL expression to normalize dates into YYYY-MM buckets."""
    return month_year_expr()


async def fetch_preferences_handler(
    preference_type: Union[PreferenceType, List[PreferenceType]] = "categorization",
    bank_name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Fetch preferences based on type(s)."""
    started_at = logger.tool_call_start(
        "fetch_preferences",
        {"preference_type": preference_type, "bank_name": bank_name, "user_id": user_id},
    )

    db = SessionLocal()
    try:
        resolved_user_id = resolve_user_id(user_id)

        if isinstance(preference_type, list):
            unique_types: List[PreferenceType] = []
            for pref_type in preference_type:
                if pref_type not in unique_types:
                    unique_types.append(pref_type)
            results: Dict[str, Any] = {}
            for pref_type in unique_types:
                results[pref_type] = (
                    await _fetch_by_type(db, resolved_user_id, pref_type, bank_name)
                )
            logger.tool_call_end("fetch_preferences", started_at, {
                "mode": "multiple",
                "types": unique_types,
            })
            return {
                "structuredContent": {
                    "kind": "multiple_preferences",
                    "types_fetched": unique_types,
                    "results": results,
                },
                "content": [{
                    "type": "text",
                    "text": f"Fetched {len(unique_types)} preference type(s).",
                }],
            }

        result = await _fetch_by_type(db, resolved_user_id, preference_type, bank_name)
        logger.tool_call_end("fetch_preferences", started_at, {
            "mode": preference_type,
        })
        return result

    except Exception as e:
        logger.tool_call_error(
            "fetch_preferences",
            started_at,
            e,
            classify_error(e),
        )
        db.rollback()
        return {
            "structuredContent": {
                "kind": "error",
                "message": str(e),
            },
            "content": [{"type": "text", "text": f"Error fetching preferences: {str(e)}"}],
        }
    finally:
        db.close()


async def _fetch_by_type(
    db,
    user_id: str,
    preference_type: PreferenceType,
    bank_name: Optional[str],
) -> dict:
    if preference_type == "settings":
        return await _fetch_user_settings(db, user_id)
    if preference_type == "parsing":
        return await _fetch_parsing_preferences(db, user_id, bank_name)
    if preference_type == "list":
        return await _fetch_list_summary(db, user_id)
    return await _fetch_categorization_preferences(db, user_id, bank_name)


async def _fetch_user_settings(db, user_id: str) -> dict:
    """Fetch user settings (functional currency, registered banks, profiles)."""
    settings_pref = (
        db.query(CategorizationPreference)
        .filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.preference_type == "settings",
            CategorizationPreference.name == SETTINGS_PREFERENCE_NAME,
            CategorizationPreference.enabled.is_(True),
        )
        .first()
    )

    settings = settings_pref.rule if settings_pref and settings_pref.rule else None
    onboarding_complete = bool(settings and settings.get("onboarding_complete"))

    return {
        "structuredContent": {
            "kind": "user_settings",
            "settings": settings,
            "onboarding_complete": onboarding_complete,
        },
        "content": [{
            "type": "text",
            "text": "Loaded user settings.",
        }],
    }


async def _fetch_categorization_preferences(db, user_id: str, bank_name: Optional[str]) -> dict:
    """Fetch categorization rules for transaction categorization."""
    query = (
        db.query(CategorizationPreference)
        .filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.enabled.is_(True),
            CategorizationPreference.preference_type == "categorization",
        )
    )

    if bank_name:
        query = query.filter(
            (CategorizationPreference.bank_name == bank_name)
            | (CategorizationPreference.bank_name.is_(None))
        )

    preferences = (
        query.order_by(
            CategorizationPreference.bank_name.is_(None),
            CategorizationPreference.priority.desc(),
            CategorizationPreference.updated_at.desc(),
        )
        .all()
    )

    result_preferences: List[Dict[str, Any]] = []
    for pref in preferences:
        result_preferences.append({
            "id": str(pref.id),
            "name": pref.name,
            "bank_name": pref.bank_name,
            "rule": pref.rule,
            "priority": pref.priority,
            "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
        })

    return {
        "structuredContent": {
            "kind": "categorization_preferences",
            "preferences": result_preferences,
            "count": len(result_preferences),
            "bank_name": bank_name,
        },
        "content": [{
            "type": "text",
            "text": f"Loaded {len(result_preferences)} categorization rule(s).",
        }],
    }


async def _fetch_parsing_preferences(db, user_id: str, bank_name: Optional[str]) -> dict:
    """Fetch parsing instructions for bank statements."""
    settings_pref = (
        db.query(CategorizationPreference)
        .filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.preference_type == "settings",
            CategorizationPreference.name == SETTINGS_PREFERENCE_NAME,
            CategorizationPreference.enabled.is_(True),
        )
        .first()
    )
    functional_currency = None
    if settings_pref and settings_pref.rule:
        functional_currency = settings_pref.rule.get("functional_currency")

    query = (
        db.query(CategorizationPreference)
        .filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.enabled.is_(True),
            CategorizationPreference.preference_type == "parsing",
        )
    )

    if bank_name:
        query = query.filter(CategorizationPreference.bank_name == bank_name)

    preferences = query.order_by(CategorizationPreference.updated_at.desc()).all()

    result_preferences: List[Dict[str, Any]] = []
    for pref in preferences:
        result_preferences.append({
            "id": str(pref.id),
            "name": pref.name,
            "bank_name": pref.bank_name,
            "instructions": pref.rule,
            "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
        })

    return {
        "structuredContent": {
            "kind": "parsing_preferences",
            "preferences": result_preferences,
            "count": len(result_preferences),
            "bank_name": bank_name,
            "functional_currency": functional_currency,
        },
        "content": [{
            "type": "text",
            "text": f"Loaded {len(result_preferences)} parsing instruction(s).",
        }],
    }


async def _fetch_list_summary(db, user_id: str) -> dict:
    """Return counts for available preferences and data."""
    total_prefs = db.query(CategorizationPreference).filter(
        CategorizationPreference.user_id == user_id,
        CategorizationPreference.enabled.is_(True),
    )

    pref_counts = (
        total_prefs
        .with_entities(CategorizationPreference.preference_type, func.count(CategorizationPreference.id))
        .group_by(CategorizationPreference.preference_type)
        .all()
    )

    pref_map = {row[0]: row[1] for row in pref_counts}
    budget_count = db.query(Budget).filter(Budget.user_id == user_id).count()
    month_expr = _month_year_expr()
    month_count = db.query(month_expr).filter(Transaction.user_id == user_id).distinct().count()

    return {
        "structuredContent": {
            "kind": "preference_summary",
            "preferences": pref_map,
            "budgets_configured": budget_count,
            "months_with_data": month_count,
        },
        "content": [{
            "type": "text",
            "text": "Loaded preference summary.",
        }],
    }
