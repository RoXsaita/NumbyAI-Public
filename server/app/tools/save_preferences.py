"""Unified tool to save preferences (settings, categorization rules, or parsing instructions)"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal

from app.database import CategorizationPreference, SessionLocal, resolve_user_id
from app.logger import classify_error, create_logger
from app.tools.category_helpers import PREDEFINED_CATEGORIES
from app.services.categorization_rules import normalize_rule_input

logger = create_logger("save_preferences")

PreferenceType = Literal["categorization", "parsing", "settings"]

# Settings preference name constant (must match fetch_preferences.py)
SETTINGS_PREFERENCE_NAME = "user_settings"

# Valid ISO 4217 currency codes (common ones)
VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY", "HKD",
    "SGD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "HRK",
    "RUB", "TRY", "ZAR", "BRL", "MXN", "ARS", "CLP", "COP", "PEN", "INR",
    "IDR", "MYR", "PHP", "THB", "VND", "KRW", "TWD", "ILS", "AED", "SAR",
    "QAR", "KWD", "BHD", "OMR", "JOD", "EGP", "NGN", "KES", "GHS", "MAD",
}


def _validate_categorization_preference(pref: Dict[str, Any], index: int) -> Optional[str]:
    """Validate a categorization preference input. Returns error message or None if valid."""
    if not isinstance(pref, dict):
        return f"Preference at index {index}: must be a dict"
    
    if "name" not in pref or not pref["name"]:
        return f"Preference at index {index}: missing required 'name' field"
    
    if "rule" not in pref:
        return f"Preference at index {index}: missing required 'rule' field"
    
    rule = pref["rule"]
    if not isinstance(rule, dict):
        return f"Preference at index {index}: 'rule' must be a dict"
    
    if "category" not in rule:
        return f"Preference at index {index}: rule must have 'category' field"
    
    if rule["category"] not in PREDEFINED_CATEGORIES:
        return f"Preference at index {index}: Invalid category '{rule['category']}'. Must be one of: {', '.join(PREDEFINED_CATEGORIES)}"

    has_pattern = any(
        key in rule for key in ("merchant_pattern", "description_pattern", "pattern", "merchant", "description", "conditions")
    )
    if not has_pattern:
        return f"Preference at index {index}: rule must include a pattern or conditions to match transactions"
    
    return None


def _validate_parsing_preference(pref: Dict[str, Any], index: int) -> Optional[str]:
    """Validate a parsing preference input. Returns error message or None if valid."""
    if not isinstance(pref, dict):
        return f"Preference at index {index}: must be a dict"
    
    if "name" not in pref or not pref["name"]:
        return f"Preference at index {index}: missing required 'name' field"
    
    if "bank_name" not in pref or not pref["bank_name"]:
        return f"Preference at index {index}: parsing preferences require 'bank_name'"
    
    instructions = pref.get("instructions", pref.get("rule"))
    if instructions is None:
        return f"Preference at index {index}: missing required 'instructions' field"

    if not isinstance(instructions, dict):
        return f"Preference at index {index}: 'instructions' must be a dict"

    # Accept both legacy parsing instructions and the bank header-mapping schema shape.
    if "steps" in instructions:
        if not isinstance(instructions.get("steps"), list):
            return f"Preference at index {index}: instructions must have 'steps' array"
        if len(instructions["steps"]) == 0:
            return f"Preference at index {index}: instructions must have at least one step"
        return None

    column_mappings = instructions.get("column_mappings")
    if not isinstance(column_mappings, dict) or len(column_mappings) == 0:
        return (
            f"Preference at index {index}: parsing schema must include non-empty "
            "'column_mappings' or legacy 'steps'"
        )
    
    return None


def _validate_settings_preference(pref: Dict[str, Any], index: int) -> Optional[str]:
    """Validate a settings preference input. Returns error message or None if valid."""
    if not isinstance(pref, dict):
        return f"Preference at index {index}: must be a dict"
    
    # functional_currency is recommended but optional
    functional_currency = pref.get("functional_currency")
    if functional_currency:
        currency_upper = functional_currency.upper().strip()
        if currency_upper not in VALID_CURRENCIES:
            return f"Preference at index {index}: Invalid currency code '{functional_currency}'. Use ISO 4217 codes (e.g., USD, EUR, GBP)"
    
    # bank_accounts_count is optional but must be positive if provided
    bank_accounts_count = pref.get("bank_accounts_count")
    if bank_accounts_count is not None:
        if not isinstance(bank_accounts_count, int) or bank_accounts_count < 0:
            return f"Preference at index {index}: bank_accounts_count must be a non-negative integer"
    
    # onboarding_complete is optional and must be boolean
    onboarding_complete = pref.get("onboarding_complete")
    if onboarding_complete is not None and not isinstance(onboarding_complete, bool):
        return f"Preference at index {index}: onboarding_complete must be a boolean"
    
    # profiles is optional but must be a list of non-empty strings
    profiles = pref.get("profiles")
    if profiles is not None:
        if not isinstance(profiles, list):
            return f"Preference at index {index}: profiles must be a list"
        for i, profile in enumerate(profiles):
            if not isinstance(profile, str) or not profile.strip():
                return f"Preference at index {index}: profiles[{i}] must be a non-empty string"
    
    # claimed_milestones is optional but must be a list of non-empty strings
    claimed_milestones = pref.get("claimed_milestones")
    if claimed_milestones is not None:
        if not isinstance(claimed_milestones, list):
            return f"Preference at index {index}: claimed_milestones must be a list"
        for i, milestone_id in enumerate(claimed_milestones):
            if not isinstance(milestone_id, str) or not milestone_id.strip():
                return f"Preference at index {index}: claimed_milestones[{i}] must be a non-empty string"
    
    # claim_milestone is optional - used to add a single milestone to claimed_milestones
    claim_milestone = pref.get("claim_milestone")
    if claim_milestone is not None:
        if not isinstance(claim_milestone, str) or not claim_milestone.strip():
            return f"Preference at index {index}: claim_milestone must be a non-empty string"
    
    # registered_banks is required for bank name validation across the app
    # This prevents bank name drift and duplications (e.g., "Revolut" vs "revolut" vs "REVOLUT")
    registered_banks = pref.get("registered_banks")
    if registered_banks is not None:
        if not isinstance(registered_banks, list):
            return f"Preference at index {index}: registered_banks must be a list"
        if len(registered_banks) == 0:
            return f"Preference at index {index}: registered_banks cannot be empty - provide at least one bank"
        seen_normalized = set()
        for i, bank in enumerate(registered_banks):
            if not isinstance(bank, str) or not bank.strip():
                return f"Preference at index {index}: registered_banks[{i}] must be a non-empty string"
            normalized = bank.strip().lower()
            if normalized in seen_normalized:
                return f"Preference at index {index}: duplicate bank name '{bank}' (case-insensitive)"
            seen_normalized.add(normalized)
    
    return None


async def save_preferences_handler(
    preferences: List[Dict[str, Any]],
    preference_type: PreferenceType = "categorization",
    user_id: Optional[str] = None
) -> dict:
    """
    Batch save preferences (settings, categorization rules, or parsing instructions).

    Args:
        preferences: List of preference objects based on type:
            
            For settings (only ONE per user - upserts):
            - registered_banks (REQUIRED for new users): List of bank names user will use
              (e.g., ["Revolut", "HSBC", "Santander"]). Case-insensitive uniqueness enforced.
              IMPORTANT: Only registered banks can be used for parsing preferences.
            - functional_currency (recommended): ISO 4217 currency code (e.g., "USD")
            - bank_accounts_count (optional): Number of bank accounts to track
            - profiles (optional): List of household profiles (e.g., ["Me", "Partner", "Joint"])
            - onboarding_complete (optional): Whether onboarding is done
            
            For categorization:
            - name (required): Human-readable rule name (e.g., "Uber rides")
            - rule (required): Structured rule with conditions and category
            - bank_name (optional): Bank name for bank-specific rule
            - priority (optional): Higher = higher priority (default 0)
            - preference_id (optional): ID to update existing preference
            
            For parsing:
            - name (required): Human-readable name (e.g., "Santander PDF Parser")
            - bank_name (required): Bank name this applies to
            - instructions (required): Structured parsing instructions
            - preference_id (optional): ID to update existing preference
            
        preference_type: "settings", "categorization", or "parsing"
        user_id: Optional user ID (defaults to test user)

    Settings structure:
        {
            "registered_banks": ["Revolut", "HSBC", "Santander"],
            "functional_currency": "USD",
            "bank_accounts_count": 3,
            "profiles": ["Me", "Partner", "Joint"],
            "onboarding_complete": true
        }

    Categorization rule structure:
        {
            "conditions": {
                "merchant": "UBER*",
                "amount_min": -100,
                "amount_max": 0
            },
            "category": "Transportation"
        }

    Parsing instructions structure:
        {
            "steps": [
                "Step 1: Identify header row...",
                "Step 2: Parse date column..."
            ],
            "key_patterns": {
                "date_format": "DD/MM/YYYY",
                "amount_column": "Debit/Credit"
            },
            "notes": "Special handling for multi-page..."
        }

    Returns:
        dict with results for each preference (created/updated/error)
    """
    started_at = logger.tool_call_start(
        "save_preferences",
        {
            "count": len(preferences),
            "preference_type": preference_type,
            "user_id": user_id,
        }
    )

    if not preferences:
        return {
            "structuredContent": {"error": "preferences list cannot be empty"},
            "content": [{"type": "text", "text": "preferences list cannot be empty"}]
        }

    # Handle settings type separately (upsert logic, only one per user)
    if preference_type == "settings":
        return await _save_user_settings(preferences, user_id, started_at)

    # Validate all inputs first based on type
    validation_errors = []
    validator = _validate_parsing_preference if preference_type == "parsing" else _validate_categorization_preference
    
    for i, pref in enumerate(preferences):
        error = validator(pref, i)
        if error:
            validation_errors.append(error)
    
    if validation_errors:
        error_text = "\n".join(validation_errors)
        return {
            "structuredContent": {"errors": validation_errors},
            "content": [{"type": "text", "text": f"Validation errors:\n{error_text}"}]
        }

    db = SessionLocal()
    results = []
    
    try:
        resolved_user_id = resolve_user_id(user_id)
        
        for pref in preferences:
            name = pref["name"]
            bank_name = pref.get("bank_name")
            preference_id = pref.get("preference_id")
            
            # Normalize bank_name
            if bank_name:
                bank_name = bank_name.strip()
                if not bank_name:
                    bank_name = None

            # Get the rule/instructions content
            if preference_type == "parsing":
                rule_content = pref.get("instructions", pref.get("rule"))
                priority = 0  # Parsing instructions don't use priority
            else:
                rule_content = normalize_rule_input(pref["rule"])
                priority = pref.get("priority", 0)

            def _build_result(action: str) -> Dict[str, Any]:
                result: Dict[str, Any] = {"action": action, "name": name}
                if preference_type == "parsing":
                    result["bank_name"] = bank_name
                else:
                    result["category"] = rule_content.get("category")
                return result

            # --- Update by ID ---
            if preference_id:
                existing = (
                    db.query(CategorizationPreference)
                    .filter(
                        CategorizationPreference.id == preference_id,
                        CategorizationPreference.user_id == resolved_user_id,
                        CategorizationPreference.preference_type == preference_type
                    )
                    .first()
                )
                if not existing:
                    results.append({"name": name, "action": "error", "error": f"Preference {preference_id} not found"})
                    continue

                existing.name = name
                existing.rule = rule_content
                existing.bank_name = bank_name
                existing.priority = priority
                existing.updated_at = datetime.now(timezone.utc)
                db.flush()
                results.append(_build_result("updated"))
                continue

            # --- Upsert for parsing preferences (unique per bank) ---
            if preference_type == "parsing":
                existing = (
                    db.query(CategorizationPreference)
                    .filter(
                        CategorizationPreference.user_id == resolved_user_id,
                        CategorizationPreference.bank_name == bank_name,
                        CategorizationPreference.preference_type == "parsing"
                    )
                    .first()
                )
                if existing:
                    existing.name = name
                    existing.rule = rule_content
                    existing.updated_at = datetime.now(timezone.utc)
                    db.flush()
                    result = _build_result("updated")
                    result["note"] = "Existing parsing instruction updated"
                    results.append(result)
                    continue

            # --- Create new ---
            new_pref = CategorizationPreference(
                user_id=resolved_user_id,
                name=name,
                rule=rule_content,
                bank_name=bank_name,
                priority=priority,
                enabled=True,
                preference_type=preference_type,
            )
            db.add(new_pref)
            db.flush()
            results.append(_build_result("created"))

        # Commit all changes in a single transaction
        db.commit()
        
        # Build summary
        created_count = sum(1 for r in results if r.get("action") == "created")
        updated_count = sum(1 for r in results if r.get("action") == "updated")
        error_count = sum(1 for r in results if r.get("action") == "error")
        
        summary_parts = []
        if created_count:
            summary_parts.append(f"{created_count} created")
        if updated_count:
            summary_parts.append(f"{updated_count} updated")
        if error_count:
            summary_parts.append(f"{error_count} errors")
        
        summary = ", ".join(summary_parts) or "No changes"
        
        # Build text output
        type_label = "parsing instructions" if preference_type == "parsing" else "categorization rules"
        text_lines = [f"Saved {type_label}: {summary}"]

        logger.tool_call_end("save_preferences", started_at, {
            "preference_type": preference_type,
            "created": created_count,
            "updated": updated_count,
            "errors": error_count,
        })

        return {
            "structuredContent": {
                "kind": f"{preference_type}_preferences_batch_result",
                "preference_type": preference_type,
                "results": results,
                "summary": {
                    "created": created_count,
                    "updated": updated_count,
                    "errors": error_count,
                }
            },
            "content": [{
                "type": "text",
                "text": "\n".join(text_lines)
            }]
        }

    except Exception as e:
        logger.tool_call_error(
            "save_preferences",
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
            "content": [{"type": "text", "text": f"Error saving preferences: {str(e)}"}]
        }
    finally:
        db.close()


async def _save_user_settings(
    preferences: List[Dict[str, Any]],
    user_id: Optional[str],
    started_at
) -> dict:
    """
    Save user settings with upsert logic (only one settings record per user).
    
    Takes the first preference object from the list and merges with existing settings.
    """
    # Validate all settings objects
    validation_errors = []
    for i, pref in enumerate(preferences):
        error = _validate_settings_preference(pref, i)
        if error:
            validation_errors.append(error)
    
    if validation_errors:
        error_text = "\n".join(validation_errors)
        return {
            "structuredContent": {"errors": validation_errors},
            "content": [{"type": "text", "text": f"Validation errors:\n{error_text}"}]
        }
    
    # Merge all preference objects into one settings dict
    # Later objects override earlier ones for the same keys
    merged_settings: Dict[str, Any] = {}
    milestones_to_claim: List[str] = []  # Collect individual claim_milestone calls
    
    for pref in preferences:
        if pref.get("functional_currency"):
            merged_settings["functional_currency"] = pref["functional_currency"].upper().strip()
        if pref.get("bank_accounts_count") is not None:
            merged_settings["bank_accounts_count"] = pref["bank_accounts_count"]
        if pref.get("onboarding_complete") is not None:
            merged_settings["onboarding_complete"] = pref["onboarding_complete"]
        if pref.get("profiles") is not None:
            # Clean and normalize profile names
            profiles = [p.strip() for p in pref["profiles"] if isinstance(p, str) and p.strip()]
            merged_settings["profiles"] = profiles
        if pref.get("claimed_milestones") is not None:
            # Clean and normalize milestone IDs
            milestones = [m.strip() for m in pref["claimed_milestones"] if isinstance(m, str) and m.strip()]
            merged_settings["claimed_milestones"] = milestones
        if pref.get("claim_milestone"):
            # Add a single milestone to claim
            milestone_id = pref["claim_milestone"].strip()
            if milestone_id:
                milestones_to_claim.append(milestone_id)
        if pref.get("registered_banks") is not None:
            # Normalize bank names: store with original casing but ensure uniqueness (case-insensitive)
            # This prevents "Revolut" vs "revolut" drift
            banks = []
            seen_lower = set()
            for bank in pref["registered_banks"]:
                if isinstance(bank, str) and bank.strip():
                    bank_clean = bank.strip()
                    bank_lower = bank_clean.lower()
                    if bank_lower not in seen_lower:
                        banks.append(bank_clean)
                        seen_lower.add(bank_lower)
            merged_settings["registered_banks"] = banks
    
    db = SessionLocal()
    try:
        resolved_user_id = resolve_user_id(user_id)
        
        # Check if settings already exist
        existing = (
            db.query(CategorizationPreference)
            .filter(
                CategorizationPreference.user_id == resolved_user_id,
                CategorizationPreference.preference_type == "settings",
                CategorizationPreference.name == SETTINGS_PREFERENCE_NAME
            )
            .first()
        )
        
        if existing:
            # Merge with existing settings
            # Copy existing rule to new dict to ensure SQLAlchemy detects the change
            current_settings = dict(existing.rule or {})
            current_settings.update(merged_settings)
            
            # Handle individual milestone claims - merge with existing claimed_milestones
            if milestones_to_claim:
                existing_milestones = set(current_settings.get("claimed_milestones", []))
                existing_milestones.update(milestones_to_claim)
                current_settings["claimed_milestones"] = sorted(list(existing_milestones))
            
            existing.rule = current_settings  # Assign new dict to trigger SQLAlchemy change detection
            existing.updated_at = datetime.now(timezone.utc)
            existing.enabled = True  # Ensure enabled
            action = "updated"
        else:
            # Create new settings
            # Handle individual milestone claims for new settings
            if milestones_to_claim:
                existing_milestones = set(merged_settings.get("claimed_milestones", []))
                existing_milestones.update(milestones_to_claim)
                merged_settings["claimed_milestones"] = sorted(list(existing_milestones))
            
            new_settings = CategorizationPreference(
                user_id=resolved_user_id,
                name=SETTINGS_PREFERENCE_NAME,
                rule=merged_settings,
                bank_name=None,
                priority=0,
                enabled=True,
                preference_type="settings",
            )
            db.add(new_settings)
            action = "created"
        
        db.commit()
        
        # Get final settings for response
        final_settings = existing.rule if existing else merged_settings
        functional_currency = final_settings.get("functional_currency", "Not set")
        bank_accounts_count = final_settings.get("bank_accounts_count")
        onboarding_complete = final_settings.get("onboarding_complete", False)
        profiles = final_settings.get("profiles", [])
        registered_banks = final_settings.get("registered_banks", [])
        
        logger.tool_call_end("save_preferences", started_at, {
            "preference_type": "settings",
            "action": action,
            "functional_currency": functional_currency,
            "profiles": profiles,
            "registered_banks": registered_banks,
        })
        
        # Build response text
        text_parts = [f"Settings {action}."]
        if functional_currency != "Not set":
            text_parts.append(f"Functional currency: {functional_currency}.")
        if registered_banks:
            text_parts.append(f"Registered banks: {', '.join(registered_banks)}.")
        if bank_accounts_count:
            text_parts.append(f"Tracking {bank_accounts_count} bank account(s).")
        if profiles:
            text_parts.append(f"Household profiles: {', '.join(profiles)}.")
        if onboarding_complete:
            text_parts.append("Onboarding complete.")
        
        return {
            "structuredContent": {
                "kind": "settings_save_result",
                "action": action,
                "settings": final_settings,
            },
            "content": [{
                "type": "text",
                "text": " ".join(text_parts)
            }]
        }
    
    except Exception as e:
        logger.tool_call_error(
            "save_preferences",
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
            "content": [{"type": "text", "text": f"Error saving settings: {str(e)}"}]
        }
    finally:
        db.close()
