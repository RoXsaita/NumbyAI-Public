"""Rule analysis service for post-hoc categorization and rule quality checks."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.database import CategorizationPreference, SessionLocal, Transaction
from app.logger import create_logger
from app.prompts import load_prompt, render_prompt
from app.services.categorization_rules import (
    CategorizationRule,
    _rule_matches_transaction,
    normalize_rule_input,
)
from app.services.llm_service import call_llm_json_array, get_llm_status
from app.tools.category_helpers import ALL_VALID_CATEGORIES, MANUAL_REVIEW, normalize_category
from app.utils import safe_emit_progress

logger = create_logger("rule_analysis_service")

FINDING_TX_CONFLICT = "tx_conflict"
FINDING_RULE_SUGGESTION = "rule_suggestion"
FINDING_RULE_FIX = "rule_fix"


@dataclass(frozen=True)
class FindingDraft:
    finding_type: str
    confidence: float
    bank_name: Optional[str]
    payload: Dict[str, Any]


def _emit(progress_callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    safe_emit_progress(progress_callback, payload, logger)


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_signature(description: str, merchant: Optional[str]) -> str:
    text = (merchant or description or "").lower()
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    words = [word for word in text.split() if len(word) > 1]
    if not words:
        return "unknown"
    return " ".join(words[:6])


def _tx_to_rule_input(tx: Transaction) -> Dict[str, Any]:
    return {
        "id": str(tx.id),
        "date": tx.date.isoformat() if tx.date else "",
        "description": tx.description or "",
        "merchant": tx.merchant or "",
        "amount": _to_float(tx.amount),
        "category": tx.category or "",
        "bank_name": tx.bank_name or "",
    }


def _tx_snapshot(tx: Transaction) -> Dict[str, Any]:
    return {
        "id": str(tx.id),
        "date": tx.date.isoformat() if tx.date else None,
        "description": tx.description,
        "merchant": tx.merchant,
        "amount": _to_float(tx.amount),
        "currency": tx.currency,
        "category": tx.category,
        "bank_name": tx.bank_name,
    }


def _rule_pattern(rule: CategorizationRule) -> str:
    rule_data = rule.rule if isinstance(rule.rule, dict) else {}
    return str(
        rule_data.get("description_pattern")
        or rule_data.get("merchant_pattern")
        or rule_data.get("pattern")
        or rule_data.get("description")
        or rule_data.get("merchant")
        or ""
    ).strip()


def _rule_pattern_kind(rule: CategorizationRule) -> str:
    rule_data = rule.rule if isinstance(rule.rule, dict) else {}
    if rule_data.get("description_pattern"):
        return "description"
    if rule_data.get("merchant_pattern"):
        return "merchant"
    return "generic"


def _rule_amount_bounds(rule: CategorizationRule) -> Tuple[Optional[str], Optional[str]]:
    rule_data = rule.rule if isinstance(rule.rule, dict) else {}
    conditions = rule_data.get("conditions") if isinstance(rule_data.get("conditions"), dict) else {}

    def _normalize_bound(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        dec = Decimal(str(value))
        normalized = format(dec.normalize(), "f")
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized

    raw_min = rule_data["amount_min"] if "amount_min" in rule_data else conditions.get("amount_min")
    raw_max = rule_data["amount_max"] if "amount_max" in rule_data else conditions.get("amount_max")
    try:
        return _normalize_bound(raw_min), _normalize_bound(raw_max)
    except Exception:
        return (
            str(raw_min).strip() if raw_min not in (None, "") else None,
            str(raw_max).strip() if raw_max not in (None, "") else None,
        )


def _normalized_pattern_text(pattern: str) -> str:
    return re.sub(r"\s+", " ", pattern.strip().lower())


def _literal_tokens(pattern: str) -> List[str]:
    unescaped = re.sub(r"\\(.)", r"\1", pattern.lower())
    stripped = re.sub(r"[\^\$\.\*\+\?\{\}\[\]\|\(\)]", " ", unescaped)
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    return [token for token in stripped.split() if len(token) > 1]


def _pattern_is_valid_regex(pattern: str) -> bool:
    if not pattern.strip():
        return True
    try:
        re.compile(pattern, re.IGNORECASE)
        return True
    except re.error:
        return False


def _rule_signature(rule: CategorizationRule, include_category: bool = True) -> str:
    amount_min, amount_max = _rule_amount_bounds(rule)
    parts = [
        _rule_pattern_kind(rule),
        _normalized_pattern_text(_rule_pattern(rule)),
        rule.bank_name or "*",
        amount_min or "*",
        amount_max or "*",
    ]
    if include_category:
        parts.append(normalize_category(str(rule.rule.get("category") or "")) or "*")
    return "|".join(parts)


def _rule_specificity(rule: CategorizationRule) -> float:
    pattern = _rule_pattern(rule)
    tokens = _literal_tokens(pattern)
    literal_chars = sum(len(token) for token in tokens)
    amount_min, amount_max = _rule_amount_bounds(rule)
    kind_bonus = {"merchant": 8.0, "description": 7.0, "generic": 5.0}.get(_rule_pattern_kind(rule), 0.0)
    bank_bonus = 12.0 if rule.bank_name else 0.0
    amount_bonus = (8.0 if amount_min is not None else 0.0) + (8.0 if amount_max is not None else 0.0)
    anchored_bonus = 2.0 if pattern.startswith("^") else 0.0
    anchored_bonus += 2.0 if pattern.endswith("$") else 0.0
    literal_bonus = min(30.0, float(literal_chars))
    token_bonus = min(12.0, float(len(set(tokens)) * 2))
    wildcard_penalty = 8.0 if literal_chars < 4 and re.search(r"[\.\*\+\?\[\]\{\}\|]", pattern) else 0.0
    return kind_bonus + bank_bonus + amount_bonus + anchored_bonus + literal_bonus + token_bonus - wildcard_penalty


def _rule_scope_overlaps(left: CategorizationRule, right: CategorizationRule) -> bool:
    return (
        left.bank_name is None
        or right.bank_name is None
        or left.bank_name == right.bank_name
    )


def _rule_sort_key(rule: CategorizationRule) -> Tuple[float, int, int]:
    return (_rule_specificity(rule), rule.priority, -len(rule.name or ""))


def _preferred_rule(matches: Sequence[Tuple[CategorizationRule, str]]) -> Tuple[CategorizationRule, str]:
    return max(matches, key=lambda item: _rule_sort_key(item[0]))


def _rules_are_shadow_related(first: CategorizationRule, second: CategorizationRule) -> bool:
    if not _rule_scope_overlaps(first, second):
        return False
    first_pattern = _rule_pattern(first)
    second_pattern = _rule_pattern(second)
    if not first_pattern or not second_pattern:
        return False
    first_tokens = set(_literal_tokens(first_pattern))
    second_tokens = set(_literal_tokens(second_pattern))
    if not first_tokens or not second_tokens:
        return False
    if not first_tokens.issubset(second_tokens):
        return False

    exemplar = " ".join(_literal_tokens(second_pattern)) or second_pattern
    try:
        if not re.search(first_pattern, exemplar, re.IGNORECASE):
            return False
    except re.error:
        if first_pattern.lower() not in exemplar.lower():
            return False
    return _rule_specificity(second) > _rule_specificity(first)


def _matching_rules_for_transaction(
    tx: Transaction,
    rules: Sequence[CategorizationRule],
) -> List[Tuple[CategorizationRule, str]]:
    tx_data = _tx_to_rule_input(tx)
    matches: List[Tuple[CategorizationRule, str]] = []
    for rule in rules:
        if rule.bank_name and rule.bank_name != tx.bank_name:
            continue
        if not isinstance(rule.rule, dict):
            continue
        if not _rule_matches_transaction(tx_data, rule.rule):
            continue
        category = normalize_category(str(rule.rule.get("category") or ""))
        if not category or category == MANUAL_REVIEW:
            continue
        matches.append((rule, category))
    return matches


def _has_equivalent_rule(
    representative_tx: Transaction,
    rules: Sequence[CategorizationRule],
    category: str,
) -> bool:
    tx_data = _tx_to_rule_input(representative_tx)
    for rule in rules:
        if rule.bank_name and rule.bank_name != representative_tx.bank_name:
            continue
        if not isinstance(rule.rule, dict):
            continue
        normalized_rule = normalize_rule_input(dict(rule.rule))
        if normalize_category(str(normalized_rule.get("category") or "")) != category:
            continue
        if _rule_matches_transaction(tx_data, normalized_rule):
            return True
    return False


def _build_suggestion_pattern(tx: Transaction, signature: str) -> str:
    candidate = (tx.merchant or "").strip()
    if not candidate:
        candidate = signature
    candidate = candidate[:60].strip()
    if not candidate:
        candidate = tx.description[:60].strip()
    if not candidate:
        candidate = ".*"
    return re.escape(candidate)


def _apply_rules_to_pending_transactions(
    transactions: Sequence[Transaction],
    rules: Sequence[CategorizationRule],
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, int]:
    """Retroactively apply current rules to pending transactions."""
    candidates = [
        tx for tx in transactions
        if tx.category == MANUAL_REVIEW or tx.review_status == "conflict"
    ]
    summary = {
        "rule_backfill_candidates": len(candidates),
        "rule_backfill_updated": 0,
        "rule_backfill_manual_resolved": 0,
        "rule_backfill_conflicts_resolved": 0,
        "rule_backfill_ambiguous": 0,
    }
    if not candidates or not rules:
        return summary

    by_id = {str(tx.id): tx for tx in transactions}
    db = SessionLocal()
    try:
        db_candidates = (
            db.query(Transaction)
            .filter(Transaction.id.in_([str(tx.id) for tx in candidates]))
            .all()
        )

        for tx in db_candidates:
            matches = _matching_rules_for_transaction(tx, rules)
            if not matches:
                continue

            matched_categories = {category for _, category in matches}
            if len(matched_categories) != 1:
                summary["rule_backfill_ambiguous"] += 1
                continue

            resolved_category = matches[0][1]
            was_manual = tx.category == MANUAL_REVIEW
            was_conflict = tx.review_status == "conflict"

            tx.category = resolved_category
            tx.category_source = "rule"
            tx.review_status = "resolved" if was_conflict else None
            tx.review_category = None
            tx.review_reason = None

            detached = by_id.get(str(tx.id))
            if detached is not None:
                detached.category = resolved_category
                detached.category_source = "rule"
                detached.review_status = "resolved" if was_conflict else None
                detached.review_category = None
                detached.review_reason = None

            summary["rule_backfill_updated"] += 1
            if was_manual:
                summary["rule_backfill_manual_resolved"] += 1
            if was_conflict:
                summary["rule_backfill_conflicts_resolved"] += 1

        db.commit()
    finally:
        db.close()

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "retro_rule_cleanup_complete",
        "summary": summary,
    })
    return summary


def _build_llm_candidates(findings: Sequence[FindingDraft]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for idx, finding in enumerate(findings):
        if finding.finding_type not in (FINDING_TX_CONFLICT, FINDING_RULE_SUGGESTION):
            continue
        payload = finding.payload
        candidates.append({
            "candidate_id": f"candidate_{idx}",
            "type": finding.finding_type,
            "bank_name": finding.bank_name,
            "current_category": payload.get("current_category"),
            "suggested_category": payload.get("suggested_category") or payload.get("category"),
            "reason": payload.get("reason"),
            "description": payload.get("transaction", {}).get("description"),
            "merchant": payload.get("transaction", {}).get("merchant"),
            "amount": payload.get("transaction", {}).get("amount"),
            "pattern": payload.get("pattern"),
            "match_count": payload.get("match_count"),
            "finding_index": idx,
        })
    return candidates


def _validate_findings_with_llm(
    findings: Sequence[FindingDraft],
) -> Optional[Dict[int, Dict[str, Any]]]:
    status = get_llm_status()
    if not status.get("available"):
        return None

    candidates = _build_llm_candidates(findings)
    if not candidates:
        return None

    prompt = render_prompt(
        load_prompt("analyze_rule_clusters.txt"),
        categories=", ".join(ALL_VALID_CATEGORIES),
        candidates=json.dumps(candidates[:200], indent=2, default=str),
    )

    response_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "decision": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["candidate_id", "decision", "confidence", "reason"],
        },
    }

    try:
        parsed = call_llm_json_array(prompt, response_schema)
    except Exception as exc:
        logger.warning("Rule analysis LLM validation failed; keeping deterministic findings", {"error": str(exc)})
        return None

    by_candidate = {item["candidate_id"]: item for item in candidates}
    decisions: Dict[int, Dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id") or "")
        match = by_candidate.get(candidate_id)
        if not match:
            continue
        decision = str(item.get("decision") or "").strip().lower()
        confidence = item.get("confidence", 0.0)
        try:
            confidence_value = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.0
        reason = str(item.get("reason") or "")[:500]
        decisions[int(match["finding_index"])] = {
            "decision": decision,
            "confidence": confidence_value,
            "reason": reason,
        }
    return decisions


def _audit_rules_catalog(
    rules: Sequence[CategorizationRule],
    add_finding: Callable[[FindingDraft, str], None],
) -> Dict[str, int]:
    summary = {
        "rules_invalid_regex": 0,
        "rules_exact_duplicates": 0,
        "rules_exact_conflicts": 0,
        "rules_scope_conflicts": 0,
    }

    for rule in rules:
        pattern = _rule_pattern(rule)
        if pattern and not _pattern_is_valid_regex(pattern):
            summary["rules_invalid_regex"] += 1
            add_finding(
                FindingDraft(
                    finding_type=FINDING_RULE_FIX,
                    confidence=0.9,
                    bank_name=rule.bank_name,
                    payload={
                        "operation": "edit",
                        "rule_id": str(rule.id),
                        "new_pattern": re.escape(pattern),
                        "reason": (
                            "Rule pattern is invalid regex and is currently falling back to literal matching. "
                            "Escaping it explicitly makes the behavior predictable."
                        ),
                    },
                ),
                dedupe_key=f"rulefix:invalid_regex:{rule.id}",
            )

    duplicate_groups: Dict[str, List[CategorizationRule]] = defaultdict(list)
    matcher_groups: Dict[str, List[CategorizationRule]] = defaultdict(list)
    for rule in rules:
        duplicate_groups[_rule_signature(rule, include_category=True)].append(rule)
        matcher_groups[_rule_signature(rule, include_category=False)].append(rule)

    for signature, grouped in duplicate_groups.items():
        if len(grouped) < 2:
            continue
        ordered = sorted(grouped, key=_rule_sort_key, reverse=True)
        primary = ordered[0]
        secondary_ids = [str(rule.id) for rule in ordered[1:]]
        if not secondary_ids:
            continue
        summary["rules_exact_duplicates"] += len(secondary_ids)
        add_finding(
            FindingDraft(
                finding_type=FINDING_RULE_FIX,
                confidence=0.96,
                bank_name=primary.bank_name,
                payload={
                    "operation": "merge",
                    "primary_rule_id": str(primary.id),
                    "secondary_rule_ids": secondary_ids,
                    "reason": "These rules have the same matcher, scope, filters, and category. Keep one and disable the duplicates.",
                    "signature": signature,
                },
            ),
            dedupe_key=f"rulefix:duplicate:{signature}",
        )

    for signature, grouped in matcher_groups.items():
        if len(grouped) < 2:
            continue
        categories = {
            normalize_category(str(rule.rule.get("category") or ""))
            for rule in grouped
            if normalize_category(str(rule.rule.get("category") or ""))
        }
        if len(categories) < 2:
            continue
        ordered = sorted(grouped, key=_rule_sort_key, reverse=True)
        preferred = ordered[0]
        secondary_ids = [str(rule.id) for rule in ordered[1:]]
        summary["rules_exact_conflicts"] += 1
        add_finding(
            FindingDraft(
                finding_type=FINDING_RULE_FIX,
                confidence=0.93,
                bank_name=preferred.bank_name,
                payload={
                    "operation": "merge",
                    "primary_rule_id": str(preferred.id),
                    "secondary_rule_ids": secondary_ids,
                    "primary_category": normalize_category(str(preferred.rule.get("category") or "")),
                    "conflicting_categories": sorted(categories),
                    "reason": "These rules use the same matcher and filters but assign different categories.",
                    "signature": signature,
                },
            ),
            dedupe_key=f"rulefix:exact_conflict:{signature}",
        )

    for idx, left in enumerate(rules):
        left_category = normalize_category(str(left.rule.get("category") or ""))
        if not left_category:
            continue
        for right in rules[idx + 1:]:
            right_category = normalize_category(str(right.rule.get("category") or ""))
            if not right_category or left_category == right_category:
                continue
            if not _rule_scope_overlaps(left, right):
                continue
            if _normalized_pattern_text(_rule_pattern(left)) != _normalized_pattern_text(_rule_pattern(right)):
                continue
            left_bounds = _rule_amount_bounds(left)
            right_bounds = _rule_amount_bounds(right)
            if left_bounds != right_bounds:
                continue

            preferred = max((left, right), key=_rule_sort_key)
            other = right if preferred is left else left
            summary["rules_scope_conflicts"] += 1
            add_finding(
                FindingDraft(
                    finding_type=FINDING_RULE_FIX,
                    confidence=0.9,
                    bank_name=preferred.bank_name or other.bank_name,
                    payload={
                        "operation": "merge",
                        "primary_rule_id": str(preferred.id),
                        "secondary_rule_ids": [str(other.id)],
                        "primary_category": normalize_category(str(preferred.rule.get("category") or "")),
                        "conflicting_categories": sorted({left_category, right_category}),
                        "reason": "Rules with overlapping scope use the same matcher but assign different categories.",
                    },
                ),
                dedupe_key=f"rulefix:scope_conflict:{min(str(left.id), str(right.id))}:{max(str(left.id), str(right.id))}",
            )

    return summary


def _suggest_rules_for_singletons(
    singletons: Sequence[Transaction],
    rules: Sequence[CategorizationRule],
    add_finding: Callable[[FindingDraft, str], None],
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """Use LLM to suggest rules for uncovered singleton transactions."""
    status = get_llm_status()
    if not status.get("available") or not singletons:
        return

    batch = []
    for tx in singletons[:100]:
        batch.append({
            "id": str(tx.id),
            "description": tx.description or "",
            "merchant": tx.merchant or "",
            "amount": _to_float(tx.amount),
            "category": tx.category or "",
            "bank_name": tx.bank_name or "",
            "date": tx.date.isoformat() if tx.date else "",
        })

    prompt = render_prompt(
        load_prompt("suggest_rules_uncovered.txt"),
        categories=", ".join(ALL_VALID_CATEGORIES),
        transactions=json.dumps(batch, indent=2, default=str),
    )

    response_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
                "pattern": {"type": "string"},
                "pattern_field": {"type": "string"},
                "category": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["transaction_id", "pattern", "category", "confidence", "reason"],
        },
    }

    try:
        parsed = call_llm_json_array(prompt, response_schema)
    except Exception as exc:
        logger.warning("Uncovered singleton LLM suggestion failed", {"error": str(exc)})
        return

    tx_by_id = {str(tx.id): tx for tx in singletons}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        tx_id = str(item.get("transaction_id") or "")
        tx = tx_by_id.get(tx_id)
        if not tx:
            continue
        pattern = str(item.get("pattern") or "").strip()
        category = str(item.get("category") or "").strip()
        if not pattern or not category:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence < 0.5:
            continue
        reason = str(item.get("reason") or "AI-suggested rule")[:500]
        pattern_field = str(item.get("pattern_field") or "description").strip()
        if pattern_field not in ("description", "merchant"):
            pattern_field = "description"

        add_finding(
            FindingDraft(
                finding_type=FINDING_RULE_SUGGESTION,
                confidence=confidence,
                bank_name=tx.bank_name,
                payload={
                    "name": f"ai:{(tx.merchant or tx.description or 'unknown')[:40]}",
                    "pattern": pattern,
                    "pattern_field": pattern_field,
                    "category": category,
                    "bank_name": tx.bank_name,
                    "match_count": 1,
                    "sample_transaction_ids": [tx_id],
                    "source": "uncovered_ai",
                    "reason": reason,
                    "llm_reason": reason,
                },
            ),
            dedupe_key=f"rulesuggest:ai:{tx.bank_name}:{pattern}:{category}",
        )


def analyze_rules_for_user(
    user_id: str,
    scope_since: date,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[List[FindingDraft], Dict[str, Any]]:
    """Analyze existing transactions and rules, returning actionable findings."""

    db = SessionLocal()
    try:
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                Transaction.date >= scope_since,
            )
            .order_by(Transaction.date.desc())
            .all()
        )
        prefs = (
            db.query(CategorizationPreference)
            .filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
                CategorizationPreference.enabled.is_(True),
            )
            .order_by(
                CategorizationPreference.bank_name.is_(None),
                CategorizationPreference.priority.desc(),
                CategorizationPreference.updated_at.desc(),
            )
            .all()
        )
    finally:
        db.close()

    rules = [
        CategorizationRule(
            id=str(pref.id),
            name=pref.name,
            bank_name=pref.bank_name,
            priority=pref.priority,
            rule=normalize_rule_input(dict(pref.rule)) if isinstance(pref.rule, dict) else {},
        )
        for pref in prefs
    ]

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "loaded",
        "transactions": len(transactions),
        "rules": len(rules),
    })

    cleanup_summary = _apply_rules_to_pending_transactions(
        transactions,
        rules,
        progress_callback=progress_callback,
    )

    findings: List[FindingDraft] = []
    dedupe_keys: set[str] = set()
    clustered: Dict[Tuple[str, str, float, str], List[Transaction]] = defaultdict(list)

    def add_finding(finding: FindingDraft, dedupe_key: str) -> None:
        if dedupe_key in dedupe_keys:
            return
        dedupe_keys.add(dedupe_key)
        findings.append(finding)

    catalog_summary = _audit_rules_catalog(rules, add_finding)

    if not transactions:
        return findings, {
            "total_findings": len(findings),
            "tx_conflict": 0,
            "rule_suggestion": 0,
            "rule_fix": len(findings),
            **catalog_summary,
            **cleanup_summary,
        }

    for tx in transactions:
        amount = _to_float(tx.amount)
        direction = "inflow" if amount > 0 else "outflow"
        signature = _normalize_signature(tx.description or "", tx.merchant)
        cluster_key = (tx.bank_name or "Unknown", signature, round(abs(amount), 2), direction)
        clustered[cluster_key].append(tx)

        current_category = normalize_category(tx.category or "")
        if tx.review_status == "conflict" and tx.review_category:
            suggested = normalize_category(tx.review_category)
            if current_category and suggested and current_category != suggested:
                add_finding(
                    FindingDraft(
                        finding_type=FINDING_TX_CONFLICT,
                        confidence=0.9,
                        bank_name=tx.bank_name,
                        payload={
                            "transaction_id": str(tx.id),
                            "transaction": _tx_snapshot(tx),
                            "current_category": current_category,
                            "suggested_category": suggested,
                            "source": "existing_review_conflict",
                            "reason": tx.review_reason or "Existing review conflict from prior processing.",
                        },
                    ),
                    dedupe_key=f"conflict:existing:{tx.id}:{suggested}",
                )

        matches = _matching_rules_for_transaction(tx, rules)
        if current_category and current_category != MANUAL_REVIEW and matches and tx.review_status != "resolved":
            preferred_rule, preferred_category = _preferred_rule(matches)
            if preferred_category != current_category:
                add_finding(
                    FindingDraft(
                        finding_type=FINDING_TX_CONFLICT,
                        confidence=0.86,
                        bank_name=tx.bank_name,
                        payload={
                            "transaction_id": str(tx.id),
                            "transaction": _tx_snapshot(tx),
                            "current_category": current_category,
                            "suggested_category": preferred_category,
                            "source": "rule_mismatch",
                            "rule_ids": [str(rule.id) for rule, _ in matches[:5]],
                            "reason": (
                                f"Transaction matches rule '{preferred_rule.name}' "
                                f"which is the strongest matching rule and maps to '{preferred_category}'."
                            ),
                        },
                    ),
                    dedupe_key=f"conflict:rule:{tx.id}:{preferred_category}",
                )

            if len(matches) > 1:
                unique_categories = {category for _, category in matches}
                if len(unique_categories) > 1:
                    leading_rule, _leading_category = matches[0]
                    if preferred_rule.id != leading_rule.id and _rules_are_shadow_related(leading_rule, preferred_rule):
                        desired_priority = max(preferred_rule.priority, leading_rule.priority + 1)
                        add_finding(
                            FindingDraft(
                                finding_type=FINDING_RULE_FIX,
                                confidence=0.9,
                                bank_name=tx.bank_name,
                                payload={
                                    "operation": "set_priority",
                                    "rule_id": str(preferred_rule.id),
                                    "new_priority": desired_priority,
                                    "shadowed_by_rule_id": str(leading_rule.id),
                                    "primary_category": preferred_category,
                                    "conflicting_categories": sorted(unique_categories),
                                    "example_transaction_id": str(tx.id),
                                    "reason": (
                                        f"Rule '{leading_rule.name}' is broader and currently shadows the more specific "
                                        f"rule '{preferred_rule.name}'."
                                    ),
                                },
                            ),
                            dedupe_key=f"rulefix:priority:{preferred_rule.id}:{leading_rule.id}",
                        )
                    else:
                        secondary_rule_ids = [str(rule.id) for rule, _ in matches if str(rule.id) != str(preferred_rule.id)][:4]
                        if secondary_rule_ids:
                            add_finding(
                                FindingDraft(
                                    finding_type=FINDING_RULE_FIX,
                                    confidence=0.72,
                                    bank_name=tx.bank_name,
                                    payload={
                                        "operation": "merge",
                                        "primary_rule_id": str(preferred_rule.id),
                                        "secondary_rule_ids": secondary_rule_ids,
                                        "primary_category": preferred_category,
                                        "conflicting_categories": sorted(unique_categories),
                                        "example_transaction_id": str(tx.id),
                                        "reason": "Multiple matching rules produce conflicting categories for the same transactions.",
                                    },
                                ),
                                dedupe_key="rulefix:merge:"
                                + "|".join(sorted([str(preferred_rule.id), *secondary_rule_ids])),
                            )

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "deterministic_scan_complete",
        "preliminary_findings": len(findings),
        "clusters": len(clustered),
    })

    for (bank_name, signature, _, _), items in clustered.items():
        if len(items) < 3:
            continue
        categories = [normalize_category(tx.category or "") for tx in items]
        categories = [cat for cat in categories if cat]
        if not categories:
            continue
        counter = Counter(categories)
        dominant, dominant_count = counter.most_common(1)[0]
        purity = dominant_count / len(items)

        if dominant != MANUAL_REVIEW and purity >= 0.8 and len(counter) > 1:
            cluster_peers = [
                _tx_snapshot(peer)
                for peer in items
                if normalize_category(peer.category or "") == dominant
            ][:3]
            for tx in items:
                tx_category = normalize_category(tx.category or "")
                if not tx_category or tx_category in (dominant, MANUAL_REVIEW):
                    continue
                if tx.review_status == "resolved":
                    continue
                add_finding(
                    FindingDraft(
                        finding_type=FINDING_TX_CONFLICT,
                        confidence=0.78,
                        bank_name=tx.bank_name,
                        payload={
                            "transaction_id": str(tx.id),
                            "transaction": _tx_snapshot(tx),
                            "current_category": tx_category,
                            "suggested_category": dominant,
                            "source": "cluster_consensus",
                            "cluster_peers": cluster_peers,
                            "cluster_total": len(items),
                            "cluster_dominant_count": dominant_count,
                            "reason": (
                                f"Recurring pattern '{signature}' is usually categorized as "
                                f"'{dominant}' ({dominant_count}/{len(items)})."
                            ),
                        },
                    ),
                    dedupe_key=f"conflict:cluster:{tx.id}:{dominant}:{signature}",
                )

        representative = items[0]
        if dominant != MANUAL_REVIEW and purity >= 0.9 and not _has_equivalent_rule(
            representative,
            rules,
            dominant,
        ):
            pattern = _build_suggestion_pattern(representative, signature)
            sample_ids = [str(tx.id) for tx in items[:10]]
            add_finding(
                FindingDraft(
                    finding_type=FINDING_RULE_SUGGESTION,
                    confidence=0.8,
                    bank_name=representative.bank_name,
                    payload={
                        "name": f"suggested:{signature[:40]}",
                        "pattern": pattern,
                        "category": dominant,
                        "bank_name": representative.bank_name,
                        "match_count": len(items),
                        "sample_transaction_ids": sample_ids,
                        "reason": (
                            f"Detected recurring pattern '{signature}' with consistent "
                            f"category '{dominant}'."
                        ),
                    },
                ),
                dedupe_key=f"rulesuggest:{representative.bank_name}:{pattern}:{dominant}",
            )

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "cluster_scan_complete",
        "preliminary_findings": len(findings),
    })

    # --- Merchant-based rule suggestions (even for 1-2 transactions) ---
    merchant_groups: Dict[Tuple[str, str], List[Transaction]] = defaultdict(list)
    for tx in transactions:
        merchant = (tx.merchant or "").strip()
        if merchant:
            merchant_groups[(tx.bank_name or "Unknown", merchant)].append(tx)

    for (bank_name, merchant), items in merchant_groups.items():
        categories = [normalize_category(tx.category or "") for tx in items]
        categories = [cat for cat in categories if cat and cat != MANUAL_REVIEW]
        if not categories:
            continue
        unique_cats = set(categories)
        if len(unique_cats) != 1:
            continue
        dominant = categories[0]
        representative = items[0]
        if _has_equivalent_rule(representative, rules, dominant):
            continue
        count = len(items)
        confidence = 0.65 if count == 1 else (0.75 if count == 2 else 0.85)
        pattern = re.escape(merchant)
        add_finding(
            FindingDraft(
                finding_type=FINDING_RULE_SUGGESTION,
                confidence=confidence,
                bank_name=bank_name if bank_name != "Unknown" else None,
                payload={
                    "name": f"merchant:{merchant[:40]}",
                    "pattern": pattern,
                    "pattern_field": "merchant",
                    "category": dominant,
                    "bank_name": bank_name if bank_name != "Unknown" else None,
                    "match_count": count,
                    "sample_transaction_ids": [str(tx.id) for tx in items[:10]],
                    "source": "merchant_match",
                    "reason": (
                        f"All {count} transaction(s) from merchant '{merchant}' "
                        f"are categorized as '{dominant}'."
                    ),
                },
            ),
            dedupe_key=f"rulesuggest:merchant:{bank_name}:{pattern}:{dominant}",
        )

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "merchant_scan_complete",
        "preliminary_findings": len(findings),
    })

    # --- Uncovered transaction detection ---
    uncovered_groups: Dict[Tuple[str, str, str], List[Transaction]] = defaultdict(list)
    uncovered_singletons: List[Transaction] = []
    for tx in transactions:
        current_cat = normalize_category(tx.category or "")
        if not current_cat or current_cat == MANUAL_REVIEW:
            continue
        if tx.review_status == "conflict":
            continue
        matches = _matching_rules_for_transaction(tx, rules)
        if matches:
            continue
        sig = _normalize_signature(tx.description or "", tx.merchant)
        key = (tx.bank_name or "Unknown", sig, current_cat)
        uncovered_groups[key].append(tx)

    for (bank_name, sig, category), items in uncovered_groups.items():
        if len(items) >= 2:
            representative = items[0]
            if _has_equivalent_rule(representative, rules, category):
                continue
            pattern = _build_suggestion_pattern(representative, sig)
            add_finding(
                FindingDraft(
                    finding_type=FINDING_RULE_SUGGESTION,
                    confidence=0.72,
                    bank_name=bank_name if bank_name != "Unknown" else None,
                    payload={
                        "name": f"uncovered:{sig[:40]}",
                        "pattern": pattern,
                        "category": category,
                        "bank_name": bank_name if bank_name != "Unknown" else None,
                        "match_count": len(items),
                        "sample_transaction_ids": [str(tx.id) for tx in items[:10]],
                        "source": "uncovered_pattern",
                        "reason": (
                            f"{len(items)} transactions matching '{sig}' are categorized "
                            f"as '{category}' but have no covering rule."
                        ),
                    },
                ),
                dedupe_key=f"rulesuggest:uncovered:{bank_name}:{sig}:{category}",
            )
        else:
            uncovered_singletons.extend(items)

    if uncovered_singletons:
        _suggest_rules_for_singletons(uncovered_singletons, rules, add_finding, progress_callback)

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "uncovered_scan_complete",
        "preliminary_findings": len(findings),
        "uncovered_singletons": len(uncovered_singletons),
    })

    llm_decisions = _validate_findings_with_llm(findings)
    if llm_decisions is not None:
        filtered: List[FindingDraft] = []
        discarded = 0
        for idx, finding in enumerate(findings):
            decision = llm_decisions.get(idx)
            if not decision:
                filtered.append(finding)
                continue
            if decision["decision"] != "keep":
                discarded += 1
                continue
            payload = dict(finding.payload)
            payload["llm_reason"] = decision["reason"]
            filtered.append(
                FindingDraft(
                    finding_type=finding.finding_type,
                    confidence=max(finding.confidence, decision["confidence"]),
                    bank_name=finding.bank_name,
                    payload=payload,
                )
            )
        findings = filtered
        _emit(progress_callback, {
            "type": "analysis_stage",
            "stage": "llm_validation_complete",
            "remaining_findings": len(findings),
            "discarded": discarded,
        })
    else:
        _emit(progress_callback, {
            "type": "analysis_stage",
            "stage": "llm_validation_skipped",
            "remaining_findings": len(findings),
        })

    counts = Counter(f.finding_type for f in findings)
    summary = {
        "total_findings": len(findings),
        FINDING_TX_CONFLICT: counts.get(FINDING_TX_CONFLICT, 0),
        FINDING_RULE_SUGGESTION: counts.get(FINDING_RULE_SUGGESTION, 0),
        FINDING_RULE_FIX: counts.get(FINDING_RULE_FIX, 0),
        **catalog_summary,
        **cleanup_summary,
    }

    _emit(progress_callback, {
        "type": "analysis_stage",
        "stage": "complete",
        "summary": summary,
    })
    return findings, summary
