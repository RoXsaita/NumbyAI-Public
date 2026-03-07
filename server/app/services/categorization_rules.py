"""Categorization rules engine for preferences.

All patterns are treated as regex (case-insensitive).  If a pattern
string is not valid regex it is automatically escaped and matched as a
literal substring.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.logger import create_logger
from app.tools.category_helpers import normalize_category

logger = create_logger("categorization_rules")


@dataclass(frozen=True)
class CategorizationRule:
    id: str
    name: str
    bank_name: Optional[str]
    priority: int
    rule: Dict[str, Any]


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _match_pattern(value: Optional[str], pattern: Any) -> bool:
    """Match *pattern* against *value* using regex (case-insensitive).

    If the pattern is not valid regex it is escaped and retried as a
    literal substring match.
    """
    if not value:
        return False
    if isinstance(pattern, list):
        return any(_match_pattern(value, p) for p in pattern)
    if not isinstance(pattern, str):
        return False
    trimmed = pattern.strip()
    if not trimmed:
        return False
    try:
        return bool(re.search(trimmed, value, re.IGNORECASE))
    except re.error:
        return bool(re.search(re.escape(trimmed), value, re.IGNORECASE))


def _extract_conditions(rule: Dict[str, Any]) -> Dict[str, Any]:
    conditions = {}
    raw_conditions = rule.get("conditions")
    if isinstance(raw_conditions, dict):
        conditions.update(raw_conditions)
    return conditions


def _match_any_field(pattern: Any, fields: List[str]) -> bool:
    """Return True if pattern matches any of the given field values."""
    return any(_match_pattern(field, pattern) for field in fields)


def _rule_matches_transaction(tx: Dict[str, Any], rule: Dict[str, Any]) -> bool:
    conditions = _extract_conditions(rule)

    description_pattern = rule.get("description_pattern") or conditions.get("description")
    merchant_pattern = rule.get("merchant_pattern") or conditions.get("merchant")
    generic_pattern = rule.get("pattern") or rule.get("merchant") or rule.get("description")

    amount_min = rule["amount_min"] if "amount_min" in rule else conditions.get("amount_min")
    amount_max = rule["amount_max"] if "amount_max" in rule else conditions.get("amount_max")

    amount_value = _to_decimal(tx.get("amount"))
    if amount_value is not None:
        min_value = _to_decimal(amount_min)
        max_value = _to_decimal(amount_max)
        if min_value is not None and amount_value < min_value:
            return False
        if max_value is not None and amount_value > max_value:
            return False

    description = tx.get("description") or ""
    merchant = tx.get("merchant") or ""
    vendor_payee = tx.get("vendor_payee") or ""
    all_fields = [description, merchant, vendor_payee]

    if description_pattern:
        return _match_any_field(description_pattern, all_fields)

    if merchant_pattern:
        return _match_any_field(merchant_pattern, [merchant, vendor_payee])

    if generic_pattern:
        return _match_any_field(generic_pattern, all_fields)

    return False


def apply_categorization_rules(
    transactions: List[Dict[str, Any]],
    rules: List[CategorizationRule]
) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
    """
    Apply categorization rules to transactions.

    Returns:
        (categorized_map, uncategorized_transactions)
    """
    categorized_map: Dict[int, str] = {}
    remaining: List[Dict[str, Any]] = []

    for tx in transactions:
        tx_id = tx.get("id")
        if tx_id is None:
            remaining.append(tx)
            continue

        existing_category = normalize_category(tx.get("category") or "")
        if existing_category:
            categorized_map[tx_id] = existing_category
            continue

        matched = None
        for rule in rules:
            if not isinstance(rule.rule, dict):
                continue
            if not _rule_matches_transaction(tx, rule.rule):
                continue
            category = normalize_category(rule.rule.get("category") or "")
            if not category:
                logger.warn("Rule category invalid; skipping", {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "category": rule.rule.get("category"),
                })
                continue
            matched = category
            break

        if matched:
            categorized_map[tx_id] = matched
        else:
            remaining.append(tx)

    return categorized_map, remaining


def format_rules_for_prompt(rules: Iterable[CategorizationRule]) -> str:
    lines: List[str] = []
    for rule in rules:
        if not isinstance(rule.rule, dict):
            continue
        category = normalize_category(rule.rule.get("category") or "")
        if not category:
            continue
        conditions = _extract_conditions(rule.rule)
        description_pattern = rule.rule.get("description_pattern") or conditions.get("description")
        merchant_pattern = rule.rule.get("merchant_pattern") or conditions.get("merchant")
        generic_pattern = rule.rule.get("pattern") or rule.rule.get("merchant") or rule.rule.get("description")
        amount_min = rule.rule["amount_min"] if "amount_min" in rule.rule else conditions.get("amount_min")
        amount_max = rule.rule["amount_max"] if "amount_max" in rule.rule else conditions.get("amount_max")

        bank_suffix = f" (bank: {rule.bank_name})" if rule.bank_name else ""
        amount_parts: List[str] = []
        if amount_min is not None:
            amount_parts.append(f"amount >= {amount_min}")
        if amount_max is not None:
            amount_parts.append(f"amount <= {amount_max}")
        amount_suffix = f" [{' and '.join(amount_parts)}]" if amount_parts else ""
        if description_pattern:
            lines.append(f"- If description/merchant matches '{description_pattern}', assign '{category}'{bank_suffix}{amount_suffix}")
        elif merchant_pattern:
            lines.append(f"- If merchant matches '{merchant_pattern}', assign '{category}'{bank_suffix}{amount_suffix}")
        elif generic_pattern:
            lines.append(f"- If merchant or description matches '{generic_pattern}', assign '{category}'{bank_suffix}{amount_suffix}")

    if not lines:
        return ""
    return "\nExisting categorization rules (apply these first):\n" + "\n".join(lines)


def normalize_rule_input(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize rule schema for persistence and evaluation.

    Migrates legacy ``pattern`` key to ``description_pattern`` and strips
    the now-unused ``pattern_type`` field.
    """
    if "pattern" in rule and "merchant_pattern" not in rule and "description_pattern" not in rule:
        rule = {**rule, "description_pattern": rule.get("pattern")}
    rule.pop("pattern_type", None)
    return rule
