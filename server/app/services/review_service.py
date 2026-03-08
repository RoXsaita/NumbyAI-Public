"""
Review Service — second-pass LLM validation of transaction categorizations.

After the primary categorizer assigns categories, this service sends all
transactions through a reviewer prompt that flags disagreements as conflicts
for human resolution.
"""
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config import settings
from app.logger import create_logger
from app.prompts import load_prompt, render_prompt
from app.services.categorization_rules import CategorizationRule, format_rules_for_prompt
from app.services.llm_service import call_llm_json_array, get_llm_status
from app.services.ollama_service import build_adaptive_batches
from app.tools.category_helpers import ALL_VALID_CATEGORIES, MANUAL_REVIEW, normalize_category
from app.utils import safe_emit_progress

logger = create_logger("review_service")

REVIEW_STATUS_CONFIRMED = "confirmed"
REVIEW_STATUS_CONFLICT = "conflict"


def _build_review_prompt(
    transactions: List[Dict[str, Any]],
    rules: List[CategorizationRule],
    extra_instructions: str = "",
) -> str:
    categories_str = ", ".join(ALL_VALID_CATEGORIES)
    rules_str = format_rules_for_prompt(rules)
    transactions_json = json.dumps(transactions, indent=2, default=str)
    template = load_prompt("review_categorization.txt")
    return render_prompt(
        template,
        categories=categories_str,
        rules=rules_str,
        transactions=transactions_json,
        extra_instructions=extra_instructions,
    )


def _call_review_model(prompt: str, llm_provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Call the configured LLM provider with the review prompt."""
    response_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "status": {"type": "string"},
                "suggested_category": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["id", "status"],
        },
    }
    return call_llm_json_array(prompt, response_schema, provider_override=llm_provider)


def _validate_review_results(
    transactions: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[int], List[str]]:
    """Validate and normalize review results from the configured LLM."""
    expected_ids = {tx["id"] for tx in transactions}
    expected_categories = {
        int(tx["id"]): normalize_category(str(tx.get("category") or ""))
        for tx in transactions
    }
    seen_ids: set[int] = set()
    normalized: List[Dict[str, Any]] = []
    errors: List[str] = []

    for item in results:
        if not isinstance(item, dict):
            errors.append("Invalid item type")
            continue
        item_id = item.get("id")
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            errors.append(f"Invalid id: {item.get('id')}")
            continue
        if item_id not in expected_ids:
            errors.append(f"Unexpected id: {item_id}")
            continue
        if item_id in seen_ids:
            errors.append(f"Duplicate id: {item_id}")
            continue

        status = str(item.get("status", "")).lower().strip()
        if status not in (REVIEW_STATUS_CONFIRMED, REVIEW_STATUS_CONFLICT):
            status = REVIEW_STATUS_CONFIRMED

        entry: Dict[str, Any] = {"id": item_id, "status": status}

        if status == REVIEW_STATUS_CONFLICT:
            suggested = normalize_category(str(item.get("suggested_category") or ""))
            if suggested and suggested != MANUAL_REVIEW:
                current = expected_categories.get(item_id)
                if current and suggested == current:
                    entry["status"] = REVIEW_STATUS_CONFIRMED
                    seen_ids.add(item_id)
                    normalized.append(entry)
                    continue
                entry["suggested_category"] = suggested
            else:
                entry["status"] = REVIEW_STATUS_CONFIRMED
                seen_ids.add(item_id)
                normalized.append(entry)
                continue
            entry["reason"] = str(item.get("reason") or "")[:500]

        seen_ids.add(item_id)
        normalized.append(entry)

    missing_ids = sorted(expected_ids - seen_ids)
    return normalized, missing_ids, errors


def review_transactions_batch(
    transactions: List[Dict[str, Any]],
    rules: List[CategorizationRule],
    batch_size: int = 20,
    max_workers: Optional[int] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    llm_provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Review categorized transactions via the configured LLM provider.

    Each transaction dict must include 'id', 'category', and the usual
    transaction fields (date, description, merchant, amount, etc.).

    Returns a list of review results:
      {"id": N, "status": "confirmed"|"conflict", "suggested_category": ..., "reason": ...}
    """
    if not transactions:
        return []

    status = get_llm_status(provider_override=llm_provider)
    if not status.get("available"):
        logger.warn("LLM unavailable for review — skipping review step")
        if progress_callback:
            progress_callback({
                "type": "review_skipped",
                "reason": "LLM not available",
            })
        return []

    batches = build_adaptive_batches(transactions, max_batch_size=batch_size)

    def emit(payload: Dict[str, Any]) -> None:
        safe_emit_progress(progress_callback, payload, logger)

    worker_limit = max_workers if max_workers is not None else settings.categorization_max_workers
    worker_limit = max(1, worker_limit)
    worker_count = min(len(batches), worker_limit)

    emit({
        "type": "review_start",
        "total_transactions": len(transactions),
        "total_batches": len(batches),
        "batch_size": batch_size,
        "parallel": len(batches) > 1,
        "max_workers": worker_count,
    })

    def review_single_batch(
        batch: List[Dict[str, Any]], batch_idx: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        emit({
            "type": "review_batch_started",
            "batch_index": batch_idx + 1,
            "total_batches": len(batches),
            "batch_size": len(batch),
        })
        batch_start = time.monotonic()
        max_attempts = 2
        attempt = 0
        last_normalized: List[Dict[str, Any]] = []
        extra_instructions = ""

        while attempt < max_attempts:
            prompt = _build_review_prompt(batch, rules, extra_instructions)
            try:
                raw = _call_review_model(prompt, llm_provider=llm_provider)
            except Exception as e:
                logger.error(f"Review batch {batch_idx + 1} LLM call failed", {"error": str(e)})
                raw = []

            normalized, missing_ids, errors = _validate_review_results(batch, raw)
            if not errors and not missing_ids:
                elapsed = int((time.monotonic() - batch_start) * 1000)
                return normalized, elapsed

            attempt += 1
            last_normalized = normalized
            missing_text = ", ".join(str(mid) for mid in missing_ids)
            error_text = "; ".join(errors[:5])
            extra_instructions = (
                f"\nPrevious output had issues: {error_text}."
                f" Return review for ALL transaction ids. Missing ids: {missing_text}."
            )

        for mid in sorted({tx["id"] for tx in batch} - {r["id"] for r in last_normalized}):
            last_normalized.append({"id": mid, "status": REVIEW_STATUS_CONFIRMED})

        elapsed = int((time.monotonic() - batch_start) * 1000)
        return last_normalized, elapsed

    all_results: List[Dict[str, Any]] = []

    if len(batches) > 1:
        batch_results: list[Optional[List[Dict[str, Any]]]] = [None] * len(batches)
        completed = 0
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(review_single_batch, batch, idx): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(future_map):
                batch_idx = future_map[future]
                try:
                    result, batch_ms = future.result()
                    batch_results[batch_idx] = result
                except Exception as e:
                    logger.error(f"Review batch {batch_idx + 1} failed", {"error": str(e)})
                    batch_results[batch_idx] = [
                        {"id": tx["id"], "status": REVIEW_STATUS_CONFIRMED}
                        for tx in batches[batch_idx]
                    ]
                    batch_ms = 0

                completed += 1
                conflicts_in_batch = sum(
                    1 for r in (batch_results[batch_idx] or [])
                    if r.get("status") == REVIEW_STATUS_CONFLICT
                )
                emit({
                    "type": "review_progress",
                    "completed_batches": completed,
                    "total_batches": len(batches),
                    "batch_index": batch_idx + 1,
                    "batch_size": len(batches[batch_idx]),
                    "reviewed": len(batch_results[batch_idx] or []),
                    "conflicts": conflicts_in_batch,
                    "duration_ms": batch_ms,
                })

        for r in batch_results:
            if r:
                all_results.extend(r)
    else:
        for idx, batch in enumerate(batches):
            try:
                single_result, batch_ms = review_single_batch(batch, idx)
            except Exception as e:
                logger.error(f"Review batch {idx + 1} failed", {"error": str(e)})
                single_result = [
                    {"id": tx["id"], "status": REVIEW_STATUS_CONFIRMED}
                    for tx in batch
                ]
                batch_ms = 0

            all_results.extend(single_result)
            conflicts_in_batch = sum(
                1 for r in single_result if r.get("status") == REVIEW_STATUS_CONFLICT
            )
            emit({
                "type": "review_progress",
                "completed_batches": idx + 1,
                "total_batches": len(batches),
                "batch_index": idx + 1,
                "batch_size": len(batch),
                "reviewed": len(single_result),
                "conflicts": conflicts_in_batch,
                "duration_ms": batch_ms,
            })

    total_conflicts = sum(1 for r in all_results if r.get("status") == REVIEW_STATUS_CONFLICT)
    total_confirmed = sum(1 for r in all_results if r.get("status") == REVIEW_STATUS_CONFIRMED)

    logger.info("Review complete", {
        "total": len(all_results),
        "confirmed": total_confirmed,
        "conflicts": total_conflicts,
    })

    emit({
        "type": "review_complete",
        "reviewed": len(all_results),
        "confirmed": total_confirmed,
        "conflicts": total_conflicts,
        "total_batches": len(batches),
    })

    return all_results
