"""
Transaction categorization service.

Uses the configured LLM provider for batch categorization.
"""
import json
import time
from collections import Counter
from typing import Dict, List, Optional, Callable, Any, Tuple

from app.config import settings
from app.services.llm_service import call_llm_json_array
from app.logger import create_logger
from app.tools.category_helpers import ALL_VALID_CATEGORIES, MANUAL_REVIEW, PREDEFINED_CATEGORIES, normalize_category
from app.prompts import load_prompt, render_prompt
from app.services.categorization_rules import CategorizationRule, format_rules_for_prompt
from app.utils import safe_emit_progress

logger = create_logger("ollama_service")

_DEFAULT_NUM_CTX = 32768
_CONTEXT_BUDGET_RATIO = 0.55
_OUTPUT_TOKENS_PER_TX = 30


# ---------------------------------------------------------------------------
# Token estimation & adaptive batching
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Conservative token estimate (~3.5 chars per token for English text)."""
    return max(1, int(len(text) / 3.5))


def _estimate_transaction_tokens(tx: Dict) -> int:
    """Estimate how many tokens a single transaction will consume in the prompt."""
    serialized = json.dumps(tx, default=str)
    return _estimate_tokens(serialized)


def _get_token_budget() -> int:
    """Compute the token budget available for the transaction payload.

    Takes the configured context window, reserves space for prompt chrome
    (template text, categories list, rules) and output tokens.
    """
    num_ctx = settings.ollama_num_ctx or _DEFAULT_NUM_CTX
    return int(num_ctx * _CONTEXT_BUDGET_RATIO)


def build_adaptive_batches(
    transactions: List[Dict],
    max_batch_size: int = 20,
    token_budget: Optional[int] = None,
) -> List[List[Dict]]:
    """Split transactions into batches that respect both count and token limits.

    Each batch will contain at most *max_batch_size* items **and** the
    estimated token cost of all items in the batch will not exceed
    *token_budget*.  A single oversized transaction still gets its own
    batch (minimum 1 per batch).
    """
    if token_budget is None:
        token_budget = _get_token_budget()

    batches: List[List[Dict]] = []
    current_batch: List[Dict] = []
    current_tokens = 0

    for tx in transactions:
        tx_tokens = _estimate_transaction_tokens(tx)

        would_exceed_tokens = current_tokens + tx_tokens > token_budget
        would_exceed_count = len(current_batch) >= max_batch_size

        if current_batch and (would_exceed_tokens or would_exceed_count):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(tx)
        current_tokens += tx_tokens

    if current_batch:
        batches.append(current_batch)

    return batches


# ---------------------------------------------------------------------------
# Prompt building & validation
# ---------------------------------------------------------------------------

def _build_categorization_prompt(
    transactions: List[Dict],
    rules: List[CategorizationRule],
    prompt_name: str,
    extra_instructions: str = "",
) -> str:
    categories_str = ", ".join(ALL_VALID_CATEGORIES)
    rules_str = format_rules_for_prompt(rules)
    transactions_json = json.dumps(transactions, indent=2, default=str)
    template = load_prompt(prompt_name)
    return render_prompt(
        template,
        categories=categories_str,
        rules=rules_str,
        transactions=transactions_json,
        extra_instructions=extra_instructions,
    )


def _validate_categorization_results(
    transactions: List[Dict],
    categorized: List[Dict],
) -> Tuple[List[Dict[str, Any]], List[int], List[str]]:
    expected_ids = {tx.get("id") for tx in transactions}
    expected_ids.discard(None)
    seen_ids: set = set()
    normalized: List[Dict[str, Any]] = []
    errors: List[str] = []

    for item in categorized:
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
        category = normalize_category(str(item.get("category") or ""))
        if not category:
            errors.append(f"Invalid category for id {item_id}: {item.get('category')}")
            continue
        seen_ids.add(item_id)
        normalized.append({"id": item_id, "category": category})

    missing_ids = sorted(expected_ids - seen_ids)
    return normalized, missing_ids, errors


# ---------------------------------------------------------------------------
# Batch categorization through the configured LLM provider
# ---------------------------------------------------------------------------

def categorize_transactions_batch(
    transactions: List[Dict],
    user_id: str,
    rules: List[CategorizationRule],
    batch_size: int = 20,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    prompt_variant: str = "default",
    llm_provider: Optional[str] = None,
) -> List[Dict]:
    """Categorize transactions via the configured LLM provider in parallel batches."""
    if not transactions:
        return []

    batches = build_adaptive_batches(transactions, max_batch_size=batch_size)

    def emit_progress(payload: Dict[str, Any]) -> None:
        safe_emit_progress(progress_callback, payload, logger)

    worker_limit = max_workers if max_workers is not None else settings.categorization_max_workers
    worker_limit = max(1, worker_limit)
    worker_count = min(len(batches), worker_limit)

    batch_sizes = [len(b) for b in batches]
    logger.info("Categorizing transactions (adaptive batching)", {
        "total": len(transactions),
        "batches": len(batches),
        "max_batch_size": batch_size,
        "actual_batch_sizes": batch_sizes,
        "token_budget": _get_token_budget(),
        "parallel": parallel,
        "max_workers": worker_count,
    })

    emit_progress({
        "type": "categorization_start",
        "total_transactions": len(transactions),
        "total_batches": len(batches),
        "batch_size": max(batch_sizes) if batch_sizes else batch_size,
        "parallel": parallel and len(batches) > 1,
        "max_workers": worker_count,
    })

    def categorize_single_batch(batch: List[Dict], batch_idx: int) -> Tuple[List[Dict], int]:
        emit_progress({
            "type": "categorization_batch_started",
            "batch_index": batch_idx + 1,
            "total_batches": len(batches),
            "batch_size": len(batch),
        })
        batch_started_at = time.monotonic()
        max_attempts = 2
        attempt = 0
        last_normalized: List[Dict[str, Any]] = []
        missing_ids: List[int] = []
        errors: List[str] = []
        extra_instructions = ""

        while attempt < max_attempts:
            result = _categorize_batch_internal(
                batch, user_id, rules, prompt_variant,
                extra_instructions=extra_instructions,
                llm_provider=llm_provider,
            )
            normalized, missing_ids, errors = _validate_categorization_results(batch, result)
            if not errors and not missing_ids:
                batch_elapsed_ms = int((time.monotonic() - batch_started_at) * 1000)
                return normalized, batch_elapsed_ms
            attempt += 1
            last_normalized = normalized
            missing_text = ", ".join(str(mid) for mid in missing_ids)
            error_text = "; ".join(errors[:5])
            extra_instructions = (
                f"\nPrevious output had issues: {error_text}."
                f" Return categories for ALL transaction ids. Missing ids: {missing_text}."
            )

        if missing_ids:
            logger.warn("Categorization output incomplete after retries — marking as MANUAL_REVIEW", {
                "missing_ids": missing_ids,
                "errors": errors,
            })
            for missing_id in missing_ids:
                last_normalized.append({"id": missing_id, "category": MANUAL_REVIEW})

        batch_elapsed_ms = int((time.monotonic() - batch_started_at) * 1000)
        return last_normalized, batch_elapsed_ms

    def _batch_category_counts(result: List[Dict]) -> Dict[str, int]:
        return dict(Counter(item.get("category", "Other") for item in result)) if result else {}

    if parallel and len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_results: List[Dict] = []
        completed_batches = 0
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_batch = {
                executor.submit(categorize_single_batch, batch, idx): idx
                for idx, batch in enumerate(batches)
            }
            batch_results: list = [None] * len(batches)
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    result, batch_elapsed_ms = future.result()
                    batch_results[batch_idx] = result
                    completed_batches += 1
                    logger.info(f"Completed batch {batch_idx + 1}/{len(batches)}", {
                        "batch_size": len(batches[batch_idx]),
                        "categorized": len(result) if result else 0,
                        "duration_ms": batch_elapsed_ms,
                    })
                    emit_progress({
                        "type": "categorization_progress",
                        "completed_batches": completed_batches,
                        "total_batches": len(batches),
                        "batch_index": batch_idx + 1,
                        "batch_size": len(batches[batch_idx]),
                        "categorized": len(result) if result else 0,
                        "categories": _batch_category_counts(result),
                        "duration_ms": batch_elapsed_ms,
                    })
                except Exception as e:
                    logger.error(f"Batch {batch_idx + 1} failed", {"error": str(e)})
                    batch_results[batch_idx] = []
                    completed_batches += 1
                    emit_progress({
                        "type": "categorization_progress",
                        "completed_batches": completed_batches,
                        "total_batches": len(batches),
                        "batch_index": batch_idx + 1,
                        "batch_size": len(batches[batch_idx]),
                        "categorized": 0,
                        "error": str(e),
                    })

            for result in batch_results:
                if result:
                    all_results.extend(result)
    else:
        all_results = []
        for idx, batch in enumerate(batches):
            try:
                result, batch_elapsed_ms = categorize_single_batch(batch, idx)
                all_results.extend(result)
                logger.info(f"Completed batch {idx + 1}/{len(batches)}", {
                    "batch_size": len(batch),
                    "categorized": len(result) if result else 0,
                    "duration_ms": batch_elapsed_ms,
                })
                emit_progress({
                    "type": "categorization_progress",
                    "completed_batches": idx + 1,
                    "total_batches": len(batches),
                    "batch_index": idx + 1,
                    "batch_size": len(batch),
                    "categorized": len(result) if result else 0,
                    "categories": _batch_category_counts(result),
                    "duration_ms": batch_elapsed_ms,
                })
            except Exception as e:
                logger.error(f"Batch {idx + 1} failed", {"error": str(e)})
                emit_progress({
                    "type": "categorization_progress",
                    "completed_batches": idx + 1,
                    "total_batches": len(batches),
                    "batch_index": idx + 1,
                    "batch_size": len(batch),
                    "categorized": 0,
                    "error": str(e),
                })

    overall_distribution = _batch_category_counts(all_results)
    other_count = overall_distribution.get("Other", 0)
    logger.info("Categorization complete", {
        "total_transactions": len(transactions),
        "categorized": len(all_results),
        "other_count": other_count,
    })

    emit_progress({
        "type": "categorization_complete",
        "categorized": len(all_results),
        "total_batches": len(batches),
        "categories": overall_distribution,
        "other_count": other_count,
    })

    return all_results


def _categorize_batch_internal(
    transactions: List[Dict],
    user_id: str,
    rules: List[CategorizationRule],
    prompt_variant: str,
    extra_instructions: str = "",
    llm_provider: Optional[str] = None,
) -> List[Dict]:
    prompt_name = "categorize_transactions.txt"
    if prompt_variant == "retry":
        prompt_name = "categorize_transactions_retry.txt"
    prompt = _build_categorization_prompt(
        transactions, rules, prompt_name,
        extra_instructions=extra_instructions,
    )
    try:
        response_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "category": {"type": "string"},
                },
                "required": ["id", "category"],
            },
        }
        return call_llm_json_array(prompt, response_schema, provider_override=llm_provider)
    except Exception as e:
        logger.error("Failed to categorize transactions", {"error": str(e)})
        return []
