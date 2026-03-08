"""Main API entry point for the NumbyAI backend."""
import asyncio
import json
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from collections import Counter
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, List, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from sqlalchemy import func, or_
from starlette.responses import JSONResponse, HTMLResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

from app.config import settings
from app.logger import create_logger
from app.tools.financial_data import get_financial_data_handler
from app.tools.fetch_preferences import fetch_preferences_handler
from app.tools.save_preferences import save_preferences_handler
from app.tools.mutate_categories import mutate_categories_handler
from app.tools.save_budget import save_budget_handler
from app.tools.category_helpers import (
    MANUAL_REVIEW,
    PREDEFINED_CATEGORIES,
    get_all_categories,
    normalize_category,
)
from app.services.llm_service import get_effective_llm_provider, get_llm_status, normalize_llm_provider
from app.services.ollama_service import categorize_transactions_batch
from app.services.review_service import review_transactions_batch
from app.services.rule_analysis_service import (
    FINDING_RULE_FIX,
    FINDING_RULE_SUGGESTION,
    FINDING_TX_CONFLICT,
    analyze_rules_for_user,
)
from app.services.categorization_rules import (
    CategorizationRule,
    apply_categorization_rules,
    normalize_rule_input,
)
from app.services.currency_service import (
    convert_amount,
    prefetch_rates_for_months,
)
from app.services.statement_analyzer import (
    check_existing_parsing_preferences,
    analyze_statement_structure_from_file,
    build_parsing_schema,
    save_parsing_schema,
)
from app.tools.statement_parser import (
    parse_csv_statement,
    normalize_transaction,
)
from app.database import (
    SessionLocal,
    Transaction,
    CategorizationPreference,
    Budget,
    CustomCategory,
    RuleAnalysisRun,
    RuleAnalysisFinding,
    get_or_create_test_user,
)
from app.auth import oauth2_auth

load_dotenv()

logger = create_logger("main")
settings.validate_production_settings()

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.parent
WEB_DIST_PATH = PROJECT_ROOT / "web" / "dist"
WEB_INDEX_PATH = WEB_DIST_PATH / "index.html"
UPLOADS_DIR = APP_ROOT.parent / "uploads"
RULE_ANALYSIS_ALL_HISTORY_SINCE = date(1900, 1, 1)
LOW_VALUE_MANUAL_REVIEW_AUTO_OTHER_CURRENCY = "PLN"
LOW_VALUE_MANUAL_REVIEW_AUTO_OTHER_THRESHOLD = Decimal("20")
RECURRING_REVIEW_MIN_AMOUNT = Decimal("10")

app = FastAPI(title="NumbyAI API")
asgi_app = app

_allowed_origins = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

WEB_DIST_PATH.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(WEB_DIST_PATH)), name="static")
logger.info("Static files mounted", {"path": "/static", "source": str(WEB_DIST_PATH)})


async def resolve_request_user_id(request: Request, require_auth: bool = False) -> str:
    """Resolve user_id from Authorization header or fall back to test user."""
    authorization = request.headers.get("Authorization")

    # When OAuth is not configured, always use the test user (local dev mode)
    if not oauth2_auth.is_enabled() and not authorization:
        return get_or_create_test_user()

    token_payload = None
    if oauth2_auth.is_enabled():
        try:
            token_payload = await oauth2_auth.validate_token(authorization)
        except HTTPException:
            if require_auth:
                raise
    if token_payload and token_payload.get("sub"):
        return str(token_payload["sub"])
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
            if payload.get("sub"):
                return str(payload["sub"])
        except Exception:
            if require_auth:
                raise HTTPException(status_code=401, detail="Invalid token")
    if require_auth:
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_or_create_test_user()


def _serialize_transactions_for_json(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized = []
    for tx in transactions:
        serialized_tx: Dict[str, Any] = {}
        for key, value in tx.items():
            if isinstance(value, Decimal):
                serialized_tx[key] = float(value)
            elif isinstance(value, (datetime, date)):
                serialized_tx[key] = value.isoformat()
            else:
                serialized_tx[key] = value
        serialized.append(serialized_tx)
    return serialized


def _add_conversion_fields(entry: Dict[str, Any], tx: Transaction) -> None:
    """Append original_amount/currency/exchange_rate to a serialized dict when present."""
    if tx.original_currency:
        entry["original_amount"] = float(tx.original_amount) if tx.original_amount is not None else None
        entry["original_currency"] = tx.original_currency
        entry["exchange_rate"] = float(tx.exchange_rate) if tx.exchange_rate is not None else None


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _should_auto_mark_small_manual_review(amount: Any, currency: Optional[str]) -> bool:
    if (currency or "").strip().upper() != LOW_VALUE_MANUAL_REVIEW_AUTO_OTHER_CURRENCY:
        return False
    normalized_amount = _coerce_decimal(amount)
    if normalized_amount is None:
        return False
    return abs(normalized_amount) <= LOW_VALUE_MANUAL_REVIEW_AUTO_OTHER_THRESHOLD


def _meets_recurring_review_floor(amount: Any) -> bool:
    normalized_amount = _coerce_decimal(amount)
    if normalized_amount is None:
        return False
    return abs(normalized_amount) >= RECURRING_REVIEW_MIN_AMOUNT


def _apply_auto_other_fallback(tx: Transaction) -> bool:
    if tx.category != MANUAL_REVIEW:
        return False
    if not _should_auto_mark_small_manual_review(tx.amount, tx.currency):
        return False

    tx.category = "Other"
    tx.category_source = tx.category_source or "ai"
    tx.review_status = None
    tx.review_category = None
    tx.review_reason = None
    tx.updated_at = datetime.now()
    return True


def _auto_resolve_low_value_manual_reviews(
    db: Any,
    user_id: str,
    bank_name: Optional[str] = None,
    created_since: Optional[datetime] = None,
) -> int:
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.category == MANUAL_REVIEW,
    )
    if bank_name:
        query = query.filter(Transaction.bank_name == bank_name)
    if created_since is not None:
        query = query.filter(Transaction.created_at >= created_since)

    updated = 0
    for tx in query.all():
        if _apply_auto_other_fallback(tx):
            updated += 1

    if updated:
        db.commit()

    return updated


def _build_transaction_payloads(
    normalized_txs: List[Dict[str, Any]],
    category_map: Dict[int, str],
    category_source_map: Dict[int, str],
    review_map: Dict[int, Dict[str, Any]],
    schema: Optional[Dict[str, Any]],
    bank_name: Optional[str],
    user_id: str,
    profile: Optional[str] = None,
    functional_currency: Optional[str] = None,
    rate_lookup: Optional[Dict[str, Optional[Decimal]]] = None,
) -> List[Dict[str, Any]]:
    default_currency = (schema or {}).get("currency", "USD")
    transaction_payloads: List[Dict[str, Any]] = []

    for idx, tx in enumerate(normalized_txs):
        tx_id = idx + 1
        tx_date = tx["date"]
        if isinstance(tx_date, str):
            tx_date = datetime.fromisoformat(tx_date).date()

        amount_value = tx.get("amount")
        if not isinstance(amount_value, Decimal):
            amount_value = Decimal(str(amount_value))

        tx_currency = tx.get("currency", default_currency)

        original_amount = None
        original_currency = None
        exchange_rate = None

        needs_conversion = (
            functional_currency
            and rate_lookup
            and tx_currency != functional_currency
        )
        if needs_conversion:
            month_key = tx_date.strftime("%Y-%m") if isinstance(tx_date, date) else None
            rate = rate_lookup.get(month_key) if month_key else None
            if rate is not None:
                original_amount = amount_value
                original_currency = tx_currency
                exchange_rate = rate
                amount_value = convert_amount(amount_value, rate)
                tx_currency = functional_currency

        review_info = review_map.get(tx_id, {})
        transaction_payloads.append({
            "user_id": user_id,
            "date": tx_date,
            "description": tx["description"],
            "merchant": tx.get("merchant"),
            "amount": amount_value,
            "currency": tx_currency,
            "original_amount": original_amount,
            "original_currency": original_currency,
            "exchange_rate": exchange_rate,
            "category": category_map.get(tx_id, MANUAL_REVIEW),
            "category_source": category_source_map.get(tx_id, "ai"),
            "bank_name": bank_name or "Unknown",
            "profile": profile or None,
            "review_status": review_info.get("review_status"),
            "review_category": review_info.get("review_category"),
            "review_reason": review_info.get("review_reason"),
        })

    return transaction_payloads


def _build_preview_transactions(
    normalized_txs: List[Dict[str, Any]],
    transaction_payloads: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    preview_txs: List[Dict[str, Any]] = []
    for tx, payload in zip(normalized_txs, transaction_payloads):
        entry = {
            **tx,
            "date": payload["date"],
            "amount": payload["amount"],
            "currency": payload["currency"],
            "category": payload["category"],
            "category_source": payload["category_source"],
            "bank_name": payload["bank_name"],
            "profile": payload["profile"],
            "review_status": payload["review_status"],
            "review_category": payload["review_category"],
            "review_reason": payload["review_reason"],
        }
        if payload.get("original_currency"):
            entry["original_amount"] = payload["original_amount"]
            entry["original_currency"] = payload["original_currency"]
            entry["exchange_rate"] = payload["exchange_rate"]
        preview_txs.append(entry)
    return preview_txs


def _apply_manual_category_override(tx: Transaction, category: str) -> str:
    normalized = normalize_category(category)
    if not normalized or normalized == MANUAL_REVIEW:
        raise ValueError(
            f"Invalid category: {category}. Must be a real spending category."
        )

    was_conflict = tx.review_status == "conflict"
    tx.category = normalized
    tx.category_source = "manual"
    tx.review_status = "resolved" if was_conflict else None
    tx.review_category = None
    tx.review_reason = None
    tx.updated_at = datetime.now()
    return normalized


@app.get("/", response_model=None)
async def root():
    """Serve the React frontend app."""
    if WEB_INDEX_PATH.exists():
        return HTMLResponse(WEB_INDEX_PATH.read_text(encoding="utf-8"))
    return JSONResponse(
        {
            "status": "ok",
            "message": "NumbyAI backend is running.",
            "hint": "Run 'cd web && npm run build' to build the frontend app.",
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    llm_status = get_llm_status()
    return JSONResponse({
        "status": "ok",
        "llm": llm_status,
        "categorization": {
            "batch_size": settings.categorization_batch_size,
            "max_workers": settings.categorization_max_workers,
        },
    })


def _read_csv_preview(
    file_path: Path,
    delimiter: str = ",",
) -> tuple[list[list[str]], int, int]:
    """Read full statement data for mapping UI (preview_data, total_rows, total_columns)."""
    import pandas as pd
    from app.services.statement_analyzer import _expected_column_count

    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        df_full = pd.read_excel(str(file_path), dtype=str, keep_default_na=False, header=None)
    else:
        csv_kwargs: dict = dict(dtype=str, keep_default_na=False, header=None, sep=delimiter)
        expected_cols = _expected_column_count(str(file_path), delimiter)
        if expected_cols and expected_cols > 1:
            csv_kwargs["names"] = list(range(expected_cols))
        df_full = pd.read_csv(str(file_path), **csv_kwargs)

    df_full = df_full.fillna("")
    preview_data: list[list[str]] = df_full.values.tolist()
    total_rows = len(df_full)
    total_columns = len(df_full.columns) if total_rows > 0 else 0

    return preview_data, total_rows, total_columns


def _parse_excluded_transaction_rows(raw_value: Any) -> List[int]:
    if raw_value is None:
        return []

    parsed_values: Any = raw_value
    if isinstance(raw_value, str):
        raw_text = raw_value.strip()
        if not raw_text:
            return []
        try:
            parsed_values = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed_values = [value.strip() for value in raw_text.split(",")]

    if not isinstance(parsed_values, list):
        return []

    rows: set[int] = set()
    for value in parsed_values:
        try:
            row_number = int(value)
        except (TypeError, ValueError):
            continue
        if row_number > 0:
            rows.add(row_number)
    return sorted(rows)


def _parse_requested_llm_provider(raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None

    raw_text = str(raw_value).strip()
    if not raw_text:
        return None

    normalized = normalize_llm_provider(raw_text)
    if normalized == "ollama":
        return normalized

    raise ValueError(
        "Invalid llm_provider. Supported value: 'ollama'."
    )


def _filter_transactions_by_source_row(
    transactions: List[Dict[str, Any]],
    excluded_rows: List[int],
) -> List[Dict[str, Any]]:
    if not excluded_rows:
        return transactions

    excluded_row_set = set(excluded_rows)
    filtered: List[Dict[str, Any]] = []
    for tx in transactions:
        source_row = tx.get("source_row_number")
        if isinstance(source_row, int) and source_row in excluded_row_set:
            continue
        filtered.append(tx)
    return filtered


_SUSPICIOUS_TX_PATTERNS: List[tuple[str, re.Pattern[str], str]] = [
    (
        "possible_reversal",
        re.compile(
            r"\b(reversal|reversed|revert|reverted|cancelled|canceled|cancel|chargeback|voided|void)\b",
            re.IGNORECASE,
        ),
        "Looks like a reversal/cancelled transaction.",
    ),
    (
        "possible_pending",
        re.compile(
            r"\b(pending|authorization|authorisation|preauthorization|preauthorisation|card hold|hold)\b",
            re.IGNORECASE,
        ),
        "Looks like pending/authorization activity.",
    ),
]


def _scan_potentially_excludable_transactions(
    transactions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    flagged: List[Dict[str, Any]] = []

    for tx in transactions:
        source_row = tx.get("source_row_number")
        if not isinstance(source_row, int):
            continue

        description = str(tx.get("description", "") or "").strip()
        vendor_payee = str(tx.get("vendor_payee", "") or "").strip()
        merchant = str(tx.get("merchant", "") or "").strip()
        scan_text = " ".join(part for part in [description, vendor_payee, merchant] if part)
        if not scan_text:
            continue

        reasons: List[Dict[str, str]] = []
        for code, pattern, label in _SUSPICIOUS_TX_PATTERNS:
            if pattern.search(scan_text):
                reasons.append({"code": code, "label": label})

        if reasons:
            amount_value = tx.get("amount", 0)
            if isinstance(amount_value, Decimal):
                amount_float = float(amount_value)
            else:
                try:
                    amount_float = float(amount_value)
                except (TypeError, ValueError):
                    amount_float = 0.0

            flagged.append({
                "source_row_number": source_row,
                "description": description,
                "amount": amount_float,
                "reasons": reasons,
            })

    return flagged


@app.post("/api/statements/upload")
async def upload_statement(request: Request) -> JSONResponse:
    """Upload and parse a bank statement (CSV/Excel)."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        form = await request.form()
        file = form.get("file")
        bank_name = form.get("bank_name")

        if not file:
            return JSONResponse({"error": "No file provided"}, status_code=400)

        filename = getattr(file, "filename", None) or "statement.csv"
        file_obj = file.file if hasattr(file, "file") else file

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_upload_dir = UPLOADS_DIR / user_id
        user_upload_dir.mkdir(exist_ok=True, parents=True)
        file_path = user_upload_dir / f"{timestamp}_{filename}"

        with open(file_path, "wb") as buffer:
            if hasattr(file_obj, "read"):
                shutil.copyfileobj(file_obj, buffer)
            else:
                buffer.write(file_obj.read() if hasattr(file_obj, "read") else file_obj)

        logger.info("File uploaded", {
            "filename": filename,
            "path": str(file_path),
            "user_id": user_id,
        })

        db = SessionLocal()
        try:
            settings_pref = db.query(CategorizationPreference).filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "settings",
                CategorizationPreference.name == "user_settings",
                CategorizationPreference.enabled.is_(True),
            ).first()
            user_currency = None
            if settings_pref and settings_pref.rule:
                user_currency = settings_pref.rule.get("functional_currency")
        finally:
            db.close()

        parsing_preferences_exist = False
        saved_mappings = None
        if bank_name:
            existing_schema = check_existing_parsing_preferences(bank_name, user_id)
            if existing_schema:
                parsing_preferences_exist = True
                saved_mappings = existing_schema
                transactions = parse_csv_statement(str(file_path), existing_schema)

                preview_data: list[list[str]] = []
                total_rows = 0
                total_columns = 0
                saved_delimiter = existing_schema.get("delimiter", ",")
                try:
                    preview_data, total_rows, total_columns = _read_csv_preview(
                        file_path, delimiter=saved_delimiter,
                    )
                except Exception as e:
                    logger.warn("Failed to read preview data for existing bank", {"error": str(e)})

                preview_transactions = _serialize_transactions_for_json(transactions)
                return JSONResponse({
                    "job_id": str(uuid.uuid4()),
                    "status": "ready_to_process",
                    "transactions_count": len(transactions),
                    "transactions": preview_transactions[:10],
                    "currency_detected": existing_schema.get("currency"),
                    "currency_required": not bool(user_currency),
                    "parsing_preferences_exist": True,
                    "detected_headers": list(existing_schema.get("column_mappings", {}).keys()) if existing_schema else [],
                    "preview_data": preview_data,
                    "total_rows": total_rows,
                    "total_columns": total_columns,
                    "saved_mappings": saved_mappings,
                })

        analysis = analyze_statement_structure_from_file(str(file_path), user_id)

        detected_headers: list[str] = []
        preview_data: list[list[str]] = []
        total_rows = 0
        total_columns = 0
        suggested_mappings = analysis.get("suggested_mappings")
        detected_delimiter = (suggested_mappings or {}).get("delimiter", ",")
        try:
            preview_data, total_rows, total_columns = _read_csv_preview(
                file_path, delimiter=detected_delimiter,
            )
            detected_headers = preview_data[0] if preview_data else []
        except Exception as e:
            logger.warn("Failed to read CSV headers/preview", {"error": str(e)})

        currency_detected = analysis.get("currency")

        return JSONResponse({
            "job_id": str(uuid.uuid4()),
            "status": "validation_required",
            "analysis": analysis,
            "suggested_mappings": suggested_mappings,
            "currency_detected": currency_detected,
            "currency_required": not bool(user_currency),
            "parsing_preferences_exist": bool(saved_mappings),
            "detected_headers": detected_headers,
            "preview_data": preview_data,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "saved_mappings": saved_mappings,
        })

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("File upload error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/statements/net-flow-preview")
async def preview_statement_net_flow(request: Request) -> JSONResponse:
    """Parse all mapped transactions and return net flow preview for mapping sanity checks."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        form = await request.form()
        file = form.get("file")
        header_mapping = form.get("header_mapping")
        bank_name = form.get("bank_name")

        if not file:
            return JSONResponse({"error": "No file provided"}, status_code=400)
        if not header_mapping:
            return JSONResponse({"error": "header_mapping is required"}, status_code=400)

        try:
            mapping_data = json.loads(str(header_mapping))
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid header_mapping JSON"}, status_code=400)
        excluded_transaction_rows = _parse_excluded_transaction_rows(
            mapping_data.get("excluded_transaction_rows")
        )

        filename = getattr(file, "filename", None) or "statement.csv"
        file_obj = file.file if hasattr(file, "file") else file

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_upload_dir = UPLOADS_DIR / user_id
        user_upload_dir.mkdir(exist_ok=True, parents=True)
        file_path = user_upload_dir / f"{timestamp}_{filename}"

        with open(file_path, "wb") as buffer:
            if hasattr(file_obj, "read"):
                shutil.copyfileobj(file_obj, buffer)
            else:
                buffer.write(file_obj.read() if hasattr(file_obj, "read") else file_obj)

        schema = _build_schema_from_header_mapping(mapping_data, user_id, bank_name)
        transactions = parse_csv_statement(str(file_path), schema)
        if not transactions:
            return JSONResponse({"error": "No transactions found with the current mapping"}, status_code=400)

        normalized_txs = [normalize_transaction(tx, schema) for tx in transactions]
        suspicious_transactions = _scan_potentially_excludable_transactions(normalized_txs)
        included_txs = _filter_transactions_by_source_row(normalized_txs, excluded_transaction_rows)
        amounts: List[Decimal] = []
        for tx in included_txs:
            amount_value = tx.get("amount")
            if isinstance(amount_value, Decimal):
                amounts.append(amount_value)
            else:
                amounts.append(Decimal(str(amount_value)))

        net_flow = sum(amounts, Decimal("0"))
        inflow_total = sum((amount for amount in amounts if amount > 0), Decimal("0"))
        outflow_total = sum((abs(amount) for amount in amounts if amount < 0), Decimal("0"))

        statement_currency = schema.get("currency", "USD")
        functional_currency = _resolve_user_currency(user_id)

        response_data: Dict[str, Any] = {
            "transaction_count": len(included_txs),
            "parsed_transaction_count": len(normalized_txs),
            "excluded_transaction_count": len(normalized_txs) - len(included_txs),
            "excluded_transaction_rows": excluded_transaction_rows,
            "net_flow": float(net_flow),
            "inflow_total": float(inflow_total),
            "outflow_total": float(outflow_total),
            "currency": statement_currency,
            "first_transaction_row": schema.get("first_transaction_row", 1),
            "invert_amount_sign": bool(schema.get("invert_amount_sign", False)),
            "suspicious_transaction_count": len(suspicious_transactions),
            "suspicious_transactions": suspicious_transactions,
        }

        if functional_currency and statement_currency != functional_currency:
            tx_dates = []
            for tx in included_txs:
                d = tx.get("date")
                if isinstance(d, str):
                    try:
                        d = datetime.fromisoformat(d).date()
                    except ValueError:
                        continue
                if isinstance(d, date):
                    tx_dates.append(d)
            if tx_dates:
                months = sorted({d.strftime("%Y-%m") for d in tx_dates})
                rate_lookup = prefetch_rates_for_months(
                    months, statement_currency, functional_currency,
                )
                converted_amounts: List[Decimal] = []
                for tx in included_txs:
                    d = tx.get("date")
                    if isinstance(d, str):
                        try:
                            d = datetime.fromisoformat(d).date()
                        except ValueError:
                            d = None
                    month_key = d.strftime("%Y-%m") if isinstance(d, date) else None
                    rate = rate_lookup.get(month_key) if month_key else None
                    amt = tx.get("amount")
                    if not isinstance(amt, Decimal):
                        amt = Decimal(str(amt))
                    if rate is not None:
                        converted_amounts.append(convert_amount(amt, rate))
                    else:
                        converted_amounts.append(amt)

                converted_net = sum(converted_amounts, Decimal("0"))
                converted_inflow = sum(
                    (a for a in converted_amounts if a > 0), Decimal("0"),
                )
                converted_outflow = sum(
                    (abs(a) for a in converted_amounts if a < 0), Decimal("0"),
                )
                response_data["converted_net_flow"] = float(converted_net)
                response_data["converted_inflow_total"] = float(converted_inflow)
                response_data["converted_outflow_total"] = float(converted_outflow)
                response_data["functional_currency"] = functional_currency

        return JSONResponse(response_data)

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Net flow preview error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


# In-memory store for dry-run preview sessions
_preview_sessions: Dict[str, Dict[str, Any]] = {}

# In-memory event logs for rule analysis SSE consumers.
_rule_analysis_event_logs: Dict[str, List[Dict[str, Any]]] = {}
_rule_analysis_event_lock = threading.Lock()


def _resolve_user_currency(user_id: str) -> str:
    db = SessionLocal()
    try:
        settings_pref = db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.preference_type == "settings",
            CategorizationPreference.name == "user_settings",
            CategorizationPreference.enabled.is_(True),
        ).first()
        if settings_pref and settings_pref.rule:
            return settings_pref.rule.get("functional_currency", "USD")
        return "USD"
    finally:
        db.close()


def _build_schema_from_header_mapping(
    mapping_data: Dict[str, Any],
    user_id: str,
    bank_name: Optional[str] = None,
) -> Dict[str, Any]:
    statement_currency = mapping_data.get("currency") or "USD"

    column_mappings = mapping_data.get("column_mappings", {})
    if not column_mappings:
        description_col = mapping_data.get("description_column", "")
        if isinstance(description_col, str):
            description_col = [description_col] if description_col else []
        elif not isinstance(description_col, list):
            description_col = []
        column_mappings = {
            "date": mapping_data.get("date_column", ""),
            "description": description_col,
            "amount": mapping_data.get("amount_column", ""),
        }
        if mapping_data.get("balance_column"):
            column_mappings["balance"] = mapping_data["balance_column"]

    schema: Dict[str, Any] = {
        "column_mappings": column_mappings,
        "date_format": mapping_data.get("date_format", "DD/MM/YYYY"),
        "currency": statement_currency,
        "number_format": mapping_data.get("number_format", "auto"),
        "delimiter": mapping_data.get("delimiter", ","),
        "has_headers": False,
        "skip_rows": 0,
        "first_transaction_row": mapping_data.get("first_transaction_row", 1),
        "amount_positive_is": mapping_data.get("amount_positive_is", "debit"),
        "invert_amount_sign": bool(mapping_data.get("invert_amount_sign", False)),
    }

    raw_inversions = mapping_data.get("amount_column_inversions", {})
    if isinstance(raw_inversions, dict):
        schema["amount_column_inversions"] = {
            str(column_ref): bool(is_inverted)
            for column_ref, is_inverted in raw_inversions.items()
        }
    else:
        schema["amount_column_inversions"] = {}

    if bank_name:
        schema["bank_name"] = bank_name

    return schema


def _rule_analysis_emit_event(run_id: str, event: Dict[str, Any]) -> None:
    payload = {
        **event,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    with _rule_analysis_event_lock:
        events = _rule_analysis_event_logs.setdefault(run_id, [])
        events.append(payload)
        if len(events) > 500:
            del events[: len(events) - 500]


def _run_rule_analysis_background(run_id: str, user_id: str, scope_since: date) -> None:
    db = SessionLocal()
    try:
        run = db.query(RuleAnalysisRun).filter(
            RuleAnalysisRun.id == run_id,
            RuleAnalysisRun.user_id == user_id,
        ).first()
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.now(tz=timezone.utc)
        db.commit()
    finally:
        db.close()

    _rule_analysis_emit_event(run_id, {
        "type": "analysis_stage",
        "stage": "started",
        "scope_since": scope_since.isoformat(),
    })

    def progress_callback(payload: Dict[str, Any]) -> None:
        _rule_analysis_emit_event(run_id, payload)

    try:
        findings, summary = analyze_rules_for_user(
            user_id=user_id,
            scope_since=scope_since,
            progress_callback=progress_callback,
        )

        db_save = SessionLocal()
        try:
            for finding in findings:
                db_save.add(RuleAnalysisFinding(
                    run_id=run_id,
                    user_id=user_id,
                    finding_type=finding.finding_type,
                    status="open",
                    confidence=round(finding.confidence, 3),
                    bank_name=finding.bank_name,
                    payload_json=finding.payload,
                ))

            run = db_save.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.id == run_id,
                RuleAnalysisRun.user_id == user_id,
            ).first()
            if run:
                run.status = "completed"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.summary_json = summary
            db_save.commit()
        finally:
            db_save.close()

        _rule_analysis_emit_event(run_id, {
            "type": "complete",
            "run_id": run_id,
            "summary": summary,
        })
    except Exception as exc:
        logger.error("Rule analysis run failed", {
            "run_id": run_id,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        db_fail = SessionLocal()
        try:
            run = db_fail.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.id == run_id,
                RuleAnalysisRun.user_id == user_id,
            ).first()
            if run:
                run.status = "failed"
                run.completed_at = datetime.now(tz=timezone.utc)
                run.error_message = str(exc)[:1000]
            db_fail.commit()
        finally:
            db_fail.close()
        _rule_analysis_emit_event(run_id, {
            "type": "error",
            "run_id": run_id,
            "error": str(exc),
        })


def _apply_rule_analysis_finding(
    db,
    user_id: str,
    finding: RuleAnalysisFinding,
    chosen_category: Optional[str] = None,
) -> Dict[str, Any]:
    payload = finding.payload_json if isinstance(finding.payload_json, dict) else {}
    finding_type = finding.finding_type

    if finding_type == FINDING_TX_CONFLICT:
        tx_id = payload.get("transaction_id")
        suggested = normalize_category(str(payload.get("suggested_category") or ""))
        selected_category = normalize_category(chosen_category or suggested)
        if not tx_id or not selected_category or selected_category == MANUAL_REVIEW:
            raise ValueError("Invalid tx_conflict finding payload")

        tx = db.query(Transaction).filter(
            Transaction.id == str(tx_id),
            Transaction.user_id == user_id,
        ).first()
        if not tx:
            raise ValueError(f"Transaction not found: {tx_id}")

        tx.category = selected_category
        tx.updated_at = datetime.now(tz=timezone.utc)
        tx.review_status = "resolved"
        tx.review_category = None
        tx.review_reason = None
        return {
            "action": "transaction_updated",
            "transaction_id": str(tx.id),
            "category": selected_category,
        }

    if finding_type == FINDING_RULE_SUGGESTION:
        pattern = str(payload.get("pattern") or "").strip()
        category = normalize_category(chosen_category or str(payload.get("category") or ""))
        bank_name = payload.get("bank_name")
        if not pattern or not category or category == MANUAL_REVIEW:
            raise ValueError("Invalid rule_suggestion finding payload")

        existing = db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.preference_type == "categorization",
            CategorizationPreference.enabled.is_(True),
            CategorizationPreference.bank_name == bank_name,
        ).all()
        for pref in existing:
            if not isinstance(pref.rule, dict):
                continue
            existing_pattern = (
                pref.rule.get("description_pattern")
                or pref.rule.get("merchant_pattern")
                or pref.rule.get("pattern")
            )
            existing_category = normalize_category(str(pref.rule.get("category") or ""))
            if existing_pattern == pattern and existing_category == category:
                return {
                    "action": "rule_exists",
                    "rule_id": str(pref.id),
                }

        new_rule = CategorizationPreference(
            user_id=user_id,
            name=str(payload.get("name") or f"suggested:{pattern[:40]}"),
            bank_name=bank_name,
            rule={
                "description_pattern": pattern,
                "category": category,
            },
            priority=10,
            enabled=True,
            preference_type="categorization",
        )
        db.add(new_rule)
        db.flush()
        return {
            "action": "rule_created",
            "rule_id": str(new_rule.id),
        }

    if finding_type == FINDING_RULE_FIX:
        operation = str(payload.get("operation") or "").strip().lower()
        if operation == "disable":
            rule_id = str(payload.get("rule_id") or "")
            if not rule_id:
                raise ValueError("Missing rule_id for disable operation")
            rule = db.query(CategorizationPreference).filter(
                CategorizationPreference.id == rule_id,
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
            ).first()
            if not rule:
                raise ValueError(f"Rule not found: {rule_id}")
            rule.enabled = False
            rule.updated_at = datetime.now(tz=timezone.utc)
            return {"action": "rule_disabled", "rule_id": rule_id}

        if operation == "edit":
            rule_id = str(payload.get("rule_id") or "")
            if not rule_id:
                raise ValueError("Missing rule_id for edit operation")
            rule = db.query(CategorizationPreference).filter(
                CategorizationPreference.id == rule_id,
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
            ).first()
            if not rule or not isinstance(rule.rule, dict):
                raise ValueError(f"Rule not found: {rule_id}")
            next_rule = dict(rule.rule)
            if payload.get("new_pattern"):
                next_rule["description_pattern"] = str(payload["new_pattern"])
            if payload.get("new_category"):
                normalized = normalize_category(str(payload["new_category"]))
                if normalized:
                    next_rule["category"] = normalized
            rule.rule = normalize_rule_input(next_rule)
            rule.updated_at = datetime.now(tz=timezone.utc)
            return {"action": "rule_edited", "rule_id": rule_id}

        if operation == "merge":
            primary_rule_id = str(payload.get("primary_rule_id") or "")
            secondary_rule_ids = [
                str(rule_id) for rule_id in payload.get("secondary_rule_ids", [])
                if str(rule_id).strip()
            ]
            if not primary_rule_id or not secondary_rule_ids:
                raise ValueError("Invalid merge operation payload")
            all_ids = [primary_rule_id, *secondary_rule_ids]
            rules = db.query(CategorizationPreference).filter(
                CategorizationPreference.id.in_(all_ids),
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
            ).all()
            found_ids = {str(rule.id) for rule in rules}
            missing = [rule_id for rule_id in all_ids if rule_id not in found_ids]
            if missing:
                raise ValueError(f"Rules not found: {', '.join(missing)}")
            for rule in rules:
                if str(rule.id) in secondary_rule_ids:
                    rule.enabled = False
                    rule.updated_at = datetime.now(tz=timezone.utc)
            return {
                "action": "rules_merged",
                "primary_rule_id": primary_rule_id,
                "disabled_rule_ids": secondary_rule_ids,
            }

        if operation == "set_priority":
            rule_id = str(payload.get("rule_id") or "")
            if not rule_id:
                raise ValueError("Missing rule_id for set_priority operation")
            try:
                new_priority = int(payload.get("new_priority"))
            except (TypeError, ValueError):
                raise ValueError("Invalid new_priority for set_priority operation")
            rule = db.query(CategorizationPreference).filter(
                CategorizationPreference.id == rule_id,
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
            ).first()
            if not rule:
                raise ValueError(f"Rule not found: {rule_id}")
            rule.priority = new_priority
            rule.updated_at = datetime.now(tz=timezone.utc)
            return {
                "action": "rule_priority_updated",
                "rule_id": rule_id,
                "priority": new_priority,
            }

        raise ValueError(f"Unsupported rule_fix operation: {operation}")

    raise ValueError(f"Unsupported finding type: {finding_type}")


def _check_statement_overlap(
    db: Any,
    user_id: str,
    bank_name: Optional[str],
    parsed_dates: List[date],
    new_count: int,
) -> Optional[Dict[str, Any]]:
    """Return duplicate warning info if significant overlap with existing transactions, else None."""
    if not bank_name or not parsed_dates or new_count == 0:
        return None
    min_date = min(parsed_dates)
    max_date = max(parsed_dates)
    existing_count: int = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.user_id == user_id,
            Transaction.bank_name == bank_name,
            Transaction.date >= min_date,
            Transaction.date <= max_date,
        )
        .scalar()
        or 0
    )
    if existing_count == 0:
        return None
    overlap_pct = round(min(existing_count, new_count) / max(existing_count, new_count) * 100)
    if overlap_pct < 70:
        return None
    return {
        "overlap_pct": overlap_pct,
        "existing_count": existing_count,
        "new_count": new_count,
        "date_min": min_date.isoformat(),
        "date_max": max_date.isoformat(),
    }


async def process_statement_pipeline(
    file_path: Path,
    bank_name: Optional[str],
    net_flow: Optional[float],
    header_mapping: Optional[str],
    user_id: str,
    excluded_transaction_rows: Optional[List[int]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    dry_run: bool = False,
    llm_provider: Optional[str] = None,
    profile: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    pipeline_start = time.monotonic()
    effective_llm_provider = get_effective_llm_provider(llm_provider)

    def emit_progress(payload: Dict[str, Any]) -> None:
        if not progress_callback:
            return
        payload["elapsed_ms"] = int((time.monotonic() - pipeline_start) * 1000)
        try:
            progress_callback(payload)
        except Exception as e:
            logger.warn("Progress callback failed", {"error": str(e)})

    schema = None
    if bank_name:
        schema = check_existing_parsing_preferences(bank_name, user_id)

    if not schema:
        if header_mapping:
            try:
                mapping_data = json.loads(header_mapping)
                schema = _build_schema_from_header_mapping(mapping_data, user_id, bank_name)

                logger.info("Built parsing schema from header mapping", {
                    "bank_name": bank_name,
                    "column_mappings": schema.get("column_mappings", {}),
                    "column_mappings_types": {
                        k: type(v).__name__
                        for k, v in schema.get("column_mappings", {}).items()
                    },
                    "amount_column_inversions": schema.get("amount_column_inversions", {}),
                    "invert_amount_sign": schema.get("invert_amount_sign", False),
                    "first_transaction_row": schema["first_transaction_row"],
                })

                if bank_name:
                    save_parsing_schema(schema, bank_name, user_id)
            except json.JSONDecodeError:
                logger.warn("Failed to parse header_mapping, falling back to analysis")
                schema = None

        if not schema:
            logger.info("No existing schema, analyzing statement structure")
            analysis = analyze_statement_structure_from_file(str(file_path), user_id)
            schema = build_parsing_schema(analysis, {})
            if bank_name:
                save_parsing_schema(schema, bank_name, user_id)

    transactions = parse_csv_statement(str(file_path), schema)
    excluded_rows = excluded_transaction_rows or []
    if excluded_rows:
        original_count = len(transactions)
        transactions = _filter_transactions_by_source_row(transactions, excluded_rows)
        logger.info("Applied transaction row exclusions", {
            "excluded_row_count": len(excluded_rows),
            "transactions_before": original_count,
            "transactions_after": len(transactions),
        })

    logger.info("Parsed %s transactions", len(transactions))

    if not transactions:
        raise ValueError("No transactions found in statement after applying exclusions")

    normalized_txs = []
    for tx in transactions:
        normalized = normalize_transaction(tx, schema)
        if normalized.get("category"):
            normalized["category"] = normalize_category(str(normalized["category"])) or None
        normalized_txs.append(normalized)

    parsed_dates = []
    for tx in normalized_txs:
        d = tx.get("date")
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d).date()
            except ValueError:
                continue
        if isinstance(d, date):
            parsed_dates.append(d)

    date_range = None
    statement_months: List[str] = []
    if parsed_dates:
        statement_months = sorted({d.strftime("%Y-%m") for d in parsed_dates})
        date_range = {
            "min": min(parsed_dates).isoformat(),
            "max": max(parsed_dates).isoformat(),
            "months": statement_months,
        }

    functional_currency = _resolve_user_currency(user_id)
    statement_currency = (schema or {}).get("currency", "USD")
    rate_lookup: Optional[Dict[str, Optional[Decimal]]] = None
    if functional_currency and statement_currency != functional_currency and statement_months:
        logger.info("Currency conversion required", {
            "statement_currency": statement_currency,
            "functional_currency": functional_currency,
            "months": statement_months,
        })
        rate_lookup = prefetch_rates_for_months(
            statement_months, statement_currency, functional_currency,
        )
        emit_progress({
            "type": "stage",
            "name": "currency_rates_fetched",
            "from_currency": statement_currency,
            "to_currency": functional_currency,
            "months": statement_months,
            "rates_found": sum(1 for r in rate_lookup.values() if r is not None),
        })

    emit_progress({
        "type": "stage",
        "name": "parsed",
        "transactions": len(transactions),
        "date_range": date_range,
    })

    if not force and not dry_run and parsed_dates:
        db_check = SessionLocal()
        try:
            dupe = _check_statement_overlap(db_check, user_id, bank_name, parsed_dates, len(normalized_txs))
            if dupe:
                return {"status": "duplicate_detected", "duplicate_warning": dupe}
        finally:
            db_check.close()

    db = SessionLocal()
    try:
        pref_query = db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.preference_type == "categorization",
            CategorizationPreference.enabled.is_(True),
        )
        if bank_name:
            pref_query = pref_query.filter(
                (CategorizationPreference.bank_name == bank_name)
                | (CategorizationPreference.bank_name.is_(None))
            )
        pref_query = pref_query.order_by(
            CategorizationPreference.bank_name.is_(None),
            CategorizationPreference.priority.desc(),
            CategorizationPreference.updated_at.desc(),
        )
        preferences = pref_query.all()
        existing_rules = [
            CategorizationRule(
                id=str(pref.id),
                name=pref.name,
                bank_name=pref.bank_name,
                priority=pref.priority,
                rule=pref.rule,
            )
            for pref in preferences
        ]
    finally:
        db.close()

    tx_with_ids = [
        {**tx, "id": idx + 1}
        for idx, tx in enumerate(normalized_txs)
    ]

    rule_category_map, uncategorized = apply_categorization_rules(tx_with_ids, existing_rules)
    llm_status = get_llm_status(provider_override=llm_provider)
    logger.info("Applied categorization rules", {
        "transaction_count": len(tx_with_ids),
        "rule_count": len(existing_rules),
        "rule_categorized": len(rule_category_map),
        "uncategorized": len(uncategorized),
        "llm_available": llm_status["available"],
        "llm_provider": effective_llm_provider,
    })

    rule_cat_distribution = dict(Counter(rule_category_map.values()))
    emit_progress({
        "type": "rule_match_summary",
        "total": len(tx_with_ids),
        "rule_matched": len(rule_category_map),
        "uncategorized": len(uncategorized),
        "rules_loaded": len(existing_rules),
        "categories": rule_cat_distribution,
    })

    if uncategorized and not llm_status["available"]:
        logger.warn("LLM unavailable; categorization will fallback to Other", {
            "provider": llm_status.get("provider"),
            "model": llm_status.get("model"),
            "error": llm_status.get("error"),
        })
        emit_progress({
            "type": "categorization_warning",
            "message": "Configured LLM not available; categorization may fall back to Other.",
            "llm_available": False,
        })

    batch_size = settings.categorization_batch_size
    logger.info("Starting parallel categorization", {
        "transaction_count": len(tx_with_ids),
        "batch_size": batch_size,
        "max_workers": settings.categorization_max_workers,
    })

    categorized = []
    if uncategorized:
        categorized = categorize_transactions_batch(
            uncategorized,
            user_id,
            existing_rules,
            batch_size=batch_size,
            parallel=True,
            max_workers=settings.categorization_max_workers,
            progress_callback=emit_progress,
            llm_provider=llm_provider,
        )

    llm_category_map = {item["id"]: item["category"] for item in categorized}
    category_source_map: Dict[int, str] = {
        tx_id: "rule" for tx_id in rule_category_map
    }
    for tx_id in llm_category_map:
        category_source_map[tx_id] = "ai"

    if uncategorized:
        manual_review_ids = [tx_id for tx_id, cat in llm_category_map.items() if cat == MANUAL_REVIEW]
        logger.info("AI categorization summary", {
            "uncategorized": len(uncategorized),
            "llm_categorized": len(llm_category_map),
            "manual_review_count": len(manual_review_ids),
        })

    category_map = {**rule_category_map, **llm_category_map}
    for tx in tx_with_ids:
        tx_id = tx["id"]
        if tx_id not in category_map:
            category_map[tx_id] = MANUAL_REVIEW
            category_source_map[tx_id] = "ai"
        elif (
            category_map[tx_id] == MANUAL_REVIEW
            and _should_auto_mark_small_manual_review(tx.get("amount"), tx.get("currency"))
        ):
            category_map[tx_id] = "Other"
            category_source_map[tx_id] = category_source_map.get(tx_id, "ai")

    final_distribution = dict(Counter(category_map.values()))
    manual_review_count = sum(1 for v in category_map.values() if v == MANUAL_REVIEW)
    auto_categorized_count = len(category_map) - manual_review_count

    # --- Review agent: second-pass validation of all categorizations ---
    review_map: Dict[int, Dict[str, Any]] = {}
    review_txs_for_llm = [
        {
            "id": tx["id"],
            "date": str(tx.get("date", "")),
            "description": tx.get("description", ""),
            "merchant": tx.get("merchant", ""),
            "amount": float(tx["amount"]) if isinstance(tx.get("amount"), Decimal) else tx.get("amount"),
            "category": category_map.get(tx["id"], MANUAL_REVIEW),
        }
        for tx in tx_with_ids
        if category_source_map.get(tx["id"]) == "ai"
        and category_map.get(tx["id"], MANUAL_REVIEW) != MANUAL_REVIEW
    ]

    review_results = review_transactions_batch(
        review_txs_for_llm,
        existing_rules,
        batch_size=batch_size,
        max_workers=settings.categorization_max_workers,
        progress_callback=emit_progress,
        llm_provider=llm_provider,
    )

    for r in review_results:
        review_tx_id = r.get("id")
        try:
            review_tx_id = int(review_tx_id)
        except (TypeError, ValueError):
            continue

        current_category = normalize_category(str(category_map.get(review_tx_id) or ""))
        suggested_category = normalize_category(str(r.get("suggested_category") or ""))
        is_true_conflict = (
            r.get("status") == "conflict"
            and current_category is not None
            and suggested_category is not None
            and current_category != suggested_category
        )

        if is_true_conflict:
            review_map[review_tx_id] = {
                "review_status": "conflict",
                "review_category": suggested_category,
                "review_reason": r.get("reason", ""),
            }
        else:
            review_map[review_tx_id] = {"review_status": "confirmed"}

    conflict_count = sum(1 for v in review_map.values() if v.get("review_status") == "conflict")
    logger.info("Review agent summary", {
        "total_reviewed": len(review_map),
        "confirmed": len(review_map) - conflict_count,
        "conflicts": conflict_count,
    })

    transaction_payloads = _build_transaction_payloads(
        normalized_txs=normalized_txs,
        category_map=category_map,
        category_source_map=category_source_map,
        review_map=review_map,
        schema=schema,
        bank_name=bank_name,
        user_id=user_id,
        profile=profile,
        functional_currency=functional_currency if rate_lookup else None,
        rate_lookup=rate_lookup,
    )

    # --- Dry-run mode: return preview without saving ---
    if dry_run:
        preview_id = str(uuid.uuid4())
        preview_txs = _build_preview_transactions(normalized_txs, transaction_payloads)

        _preview_sessions[preview_id] = {
            "transaction_payloads": transaction_payloads,
            "bank_name": bank_name,
            "user_id": user_id,
            "created_at": time.monotonic(),
        }

        emit_progress({
            "type": "stage",
            "name": "preview_ready",
            "transactions": len(normalized_txs),
            "categories": final_distribution,
        })

        return {
            "status": "preview",
            "preview_id": preview_id,
            "transactions_processed": len(normalized_txs),
            "transactions": _serialize_transactions_for_json(preview_txs[:20]),
            "manual_review_count": manual_review_count,
            "auto_categorized_count": auto_categorized_count,
            "category_distribution": final_distribution,
        }

    # --- Normal mode: save to database ---
    logger.info("Saving individual transactions to database", {
        "transaction_count": len(normalized_txs),
        "bank_name": bank_name,
    })

    db_save = SessionLocal()
    try:
        for payload in transaction_payloads:
            transaction = Transaction(**payload)
            db_save.add(transaction)

        db_save.commit()
        logger.info("Saved %s transactions to database", len(normalized_txs))
    except Exception as e:
        db_save.rollback()
        logger.error("Failed to save transactions to database", {
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        db_save.close()

    emit_progress({
        "type": "stage",
        "name": "transactions_saved",
        "transactions": len(normalized_txs),
        "categories": final_distribution,
        "manual_review_count": manual_review_count,
        "conflict_count": conflict_count,
    })

    dashboard_data = get_financial_data_handler(
        user_id=user_id,
        bank_name=bank_name,
        month_year=None,
    )

    emit_progress({
        "type": "stage",
        "name": "dashboard_ready",
    })

    category_count = len({cat for cat in category_map.values() if cat})

    return {
        "status": "success",
        "transactions_processed": len(normalized_txs),
        "categories": category_count,
        "manual_review_count": manual_review_count,
        "conflict_count": conflict_count,
        "dashboard": dashboard_data,
        "message": (
            f"Successfully processed {len(normalized_txs)} transactions across "
            f"{category_count} categories"
        ),
    }


@app.post("/api/statements/process")
async def process_statement_automatically(request: Request) -> JSONResponse:
    """
    Automatic statement processing: upload → parse → categorize → save → dashboard.
    """
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)

        form = await request.form()
        file = form.get("file")
        bank_name = form.get("bank_name")
        profile = form.get("profile") or None
        net_flow_str = form.get("net_flow")
        header_mapping = form.get("header_mapping")
        try:
            llm_provider = _parse_requested_llm_provider(form.get("llm_provider"))
        except ValueError as exc:
            return JSONResponse({"error": str(exc), "status": "error"}, status_code=400)
        excluded_transaction_rows = _parse_excluded_transaction_rows(
            form.get("excluded_transaction_rows")
        )
        force = str(form.get("force", "false")).lower() in ("true", "1", "yes")

        if not file:
            return JSONResponse({"error": "No file provided"}, status_code=400)

        filename = getattr(file, "filename", None) or "statement.csv"
        file_obj = file.file if hasattr(file, "file") else file

        net_flow = None
        if net_flow_str:
            try:
                net_flow = float(net_flow_str)
            except (ValueError, TypeError):
                pass

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_upload_dir = UPLOADS_DIR / user_id
        user_upload_dir.mkdir(exist_ok=True, parents=True)
        file_path = user_upload_dir / f"{timestamp}_{filename}"

        with open(file_path, "wb") as buffer:
            if hasattr(file_obj, "read"):
                shutil.copyfileobj(file_obj, buffer)
            else:
                buffer.write(file_obj.read() if hasattr(file_obj, "read") else file_obj)

        logger.info("Auto-processing statement", {
            "filename": filename,
            "bank_name": bank_name,
            "profile": profile,
            "user_id": user_id,
            "has_header_mapping": bool(header_mapping),
            "llm_provider": get_effective_llm_provider(llm_provider),
            "excluded_row_count": len(excluded_transaction_rows),
        })

        try:
            result = await process_statement_pipeline(
                file_path=file_path,
                bank_name=bank_name,
                net_flow=net_flow,
                header_mapping=header_mapping,
                user_id=user_id,
                excluded_transaction_rows=excluded_transaction_rows,
                llm_provider=llm_provider,
                profile=profile,
                force=force,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e), "status": "error"}, status_code=400)

        return JSONResponse(result)

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Auto-processing error", {
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.post("/api/statements/process-stream")
async def process_statement_stream(request: Request):
    """Stream statement processing progress while categorizing in parallel batches."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)

        form = await request.form()
        file = form.get("file")
        bank_name = form.get("bank_name")
        profile = form.get("profile") or None
        net_flow_str = form.get("net_flow")
        header_mapping = form.get("header_mapping")
        try:
            llm_provider = _parse_requested_llm_provider(form.get("llm_provider"))
        except ValueError as exc:
            return JSONResponse({"error": str(exc), "status": "error"}, status_code=400)
        excluded_transaction_rows = _parse_excluded_transaction_rows(
            form.get("excluded_transaction_rows")
        )

        if not file:
            return JSONResponse({"error": "No file provided"}, status_code=400)

        filename = getattr(file, "filename", None) or "statement.csv"
        file_obj = file.file if hasattr(file, "file") else file

        net_flow = None
        if net_flow_str:
            try:
                net_flow = float(net_flow_str)
            except (ValueError, TypeError):
                pass

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_upload_dir = UPLOADS_DIR / user_id
        user_upload_dir.mkdir(exist_ok=True, parents=True)
        file_path = user_upload_dir / f"{timestamp}_{filename}"

        with open(file_path, "wb") as buffer:
            if hasattr(file_obj, "read"):
                shutil.copyfileobj(file_obj, buffer)
            else:
                buffer.write(file_obj.read() if hasattr(file_obj, "read") else file_obj)

        dry_run_str = form.get("dry_run", "false")
        is_dry_run = dry_run_str in ("true", "1", "yes")
        force = str(form.get("force", "false")).lower() in ("true", "1", "yes")

        logger.info("Auto-processing statement (streaming)", {
            "filename": filename,
            "bank_name": bank_name,
            "profile": profile,
            "user_id": user_id,
            "has_header_mapping": bool(header_mapping),
            "llm_provider": get_effective_llm_provider(llm_provider),
            "dry_run": is_dry_run,
            "excluded_row_count": len(excluded_transaction_rows),
        })

        server_started_at = datetime.now(tz=timezone.utc).isoformat()

        progress_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        progress_queue.put({
            "type": "stage",
            "name": "file_saved",
            "filename": filename,
            "server_started_at": server_started_at,
        })

        def progress_callback(payload: Dict[str, Any]) -> None:
            progress_queue.put(payload)

        def worker() -> None:
            try:
                result = asyncio.run(process_statement_pipeline(
                    file_path=file_path,
                    bank_name=bank_name,
                    net_flow=net_flow,
                    header_mapping=header_mapping,
                    user_id=user_id,
                    excluded_transaction_rows=excluded_transaction_rows,
                    progress_callback=progress_callback,
                    dry_run=is_dry_run,
                    llm_provider=llm_provider,
                    profile=profile,
                    force=force,
                ))
                progress_queue.put({"type": "complete", "result": result})
            except Exception as e:
                logger.error("Auto-processing stream error", {
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
                progress_queue.put({"type": "error", "error": str(e)})

        threading.Thread(target=worker, daemon=True).start()

        async def event_generator():
            while True:
                event = await asyncio.to_thread(progress_queue.get)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Auto-processing stream error", {
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.post("/api/statements/commit")
async def commit_preview(request: Request) -> JSONResponse:
    """Commit a dry-run preview session — saves the already-categorized transactions."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        preview_id = data.get("preview_id")

        if not preview_id or preview_id not in _preview_sessions:
            return JSONResponse({"error": "Invalid or expired preview session"}, status_code=400)

        session = _preview_sessions.pop(preview_id)
        if session["user_id"] != user_id:
            return JSONResponse({"error": "Unauthorized"}, status_code=403)

        transaction_payloads = session["transaction_payloads"]
        bank_name = session["bank_name"]

        db_save = SessionLocal()
        try:
            for payload in transaction_payloads:
                db_save.add(Transaction(**payload))

            db_save.commit()
            logger.info("Committed preview session", {
                "preview_id": preview_id,
                "transaction_count": len(transaction_payloads),
            })
        except Exception as e:
            db_save.rollback()
            raise
        finally:
            db_save.close()

        manual_review_count = sum(
            1 for payload in transaction_payloads if payload["category"] == MANUAL_REVIEW
        )

        dashboard_data = get_financial_data_handler(
            user_id=user_id,
            bank_name=bank_name,
            month_year=None,
        )

        return JSONResponse({
            "status": "success",
            "transactions_processed": len(transaction_payloads),
            "manual_review_count": manual_review_count,
            "dashboard": dashboard_data,
        })

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Commit preview error", {"error": str(e), "traceback": traceback.format_exc()})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/transactions")
async def get_transactions(request: Request) -> JSONResponse:
    """List transactions with filters."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            query = db.query(Transaction).filter(Transaction.user_id == user_id)

            bank_name = request.query_params.get("bank_name")
            category = request.query_params.get("category")
            date_from = request.query_params.get("date_from")
            date_to = request.query_params.get("date_to")

            if bank_name:
                query = query.filter(Transaction.bank_name == bank_name)
            if category:
                query = query.filter(Transaction.category == category)
            if date_from:
                query = query.filter(Transaction.date >= date_from)
            if date_to:
                query = query.filter(Transaction.date <= date_to)

            transactions = query.order_by(Transaction.date.desc()).limit(1000).all()
            result = []
            for tx in transactions:
                entry = {
                    "id": str(tx.id),
                    "date": tx.date.isoformat() if tx.date else None,
                    "description": tx.description,
                    "merchant": tx.merchant,
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "category": tx.category,
                    "category_source": tx.category_source,
                    "bank_name": tx.bank_name,
                    "profile": tx.profile,
                }
                _add_conversion_fields(entry, tx)
                result.append(entry)
            return JSONResponse({"transactions": result, "count": len(result)})
        finally:
            db.close()

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get transactions error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.patch("/api/transactions")
async def update_transaction(request: Request) -> JSONResponse:
    """Update a transaction."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        tx_id = data.get("id")
        updates = data.get("updates", {})

        if not tx_id:
            return JSONResponse({"error": "Transaction ID is required"}, status_code=400)

        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(
                Transaction.id == tx_id,
                Transaction.user_id == user_id,
            ).first()

            if not tx:
                return JSONResponse({"error": "Transaction not found"}, status_code=404)

            normalized_category: Optional[str] = None
            if "category" in updates:
                try:
                    normalized_category = _apply_manual_category_override(tx, updates["category"])
                except ValueError as exc:
                    return JSONResponse({"error": str(exc)}, status_code=400)
            if "merchant" in updates:
                tx.merchant = updates["merchant"]
            if "description" in updates:
                tx.description = updates["description"]

            tx.updated_at = datetime.now()
            db.commit()

            return JSONResponse({
                "id": str(tx.id),
                "category": normalized_category or tx.category,
                "category_source": tx.category_source,
                "review_status": tx.review_status,
                "review_category": tx.review_category,
                "review_reason": tx.review_reason,
                "updated": True,
            })
        finally:
            db.close()

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Update transaction error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/financial-data")
async def get_financial_data_api(request: Request) -> JSONResponse:
    """Return dashboard data."""
    try:
        user_id = await resolve_request_user_id(request)

        bank_name = request.query_params.get("bank_name")
        month_year = request.query_params.get("month_year")
        categories = request.query_params.getlist("categories")
        profile = request.query_params.get("profile")

        result = get_financial_data_handler(
            user_id=user_id,
            bank_name=bank_name,
            month_year=month_year,
            categories=categories if categories else None,
            profile=profile,
        )

        return JSONResponse(result)

    except Exception as e:
        logger.error("Get financial data error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/mutate-categories")
async def mutate_categories_api(request: Request) -> JSONResponse:
    """Edit or transfer category totals."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        operations = data.get("operations", [])
        bank_name = data.get("bank_name")
        month_year = data.get("month_year")

        result = mutate_categories_handler(
            operations=operations,
            user_id=user_id,
            bank_name=bank_name,
            month_year=month_year,
        )
        return JSONResponse(result)

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Mutate categories error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/budgets")
@app.post("/api/budgets")
async def manage_budgets(request: Request) -> JSONResponse:
    """Get or save budgets."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=request.method != "GET")

        if request.method == "GET":
            db = SessionLocal()
            try:
                budgets = db.query(Budget).filter(Budget.user_id == user_id).all()
                result = [{
                    "category": b.category,
                    "month_year": b.month_year,
                    "amount": float(b.amount),
                    "currency": b.currency,
                } for b in budgets]
                return JSONResponse({"budgets": result})
            finally:
                db.close()

        data = await request.json()
        budgets = data.get("budgets", [])
        result = await save_budget_handler(budgets=budgets, user_id=user_id)
        return JSONResponse(result.get("structuredContent", {"status": "saved"}))

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Manage budgets error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/preferences")
@app.post("/api/preferences")
async def manage_preferences_api(request: Request) -> JSONResponse:
    """Get or save preferences."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=request.method != "GET")

        if request.method == "GET":
            preference_type = request.query_params.get("preference_type", "categorization")
            bank_name = request.query_params.get("bank_name")

            result = await fetch_preferences_handler(
                preference_type=preference_type,
                bank_name=bank_name,
                user_id=user_id,
            )
            return JSONResponse(result.get("structuredContent", {}))

        data = await request.json()
        preferences = data.get("preferences", [])
        preference_type = data.get("preference_type", "categorization")

        result = await save_preferences_handler(
            preferences=preferences,
            preference_type=preference_type,
            user_id=user_id,
        )

        return JSONResponse(result.get("structuredContent", {"status": "saved"}))

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Preferences API error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/preferences/{preference_id}")
async def delete_preference_api(request: Request, preference_id: str) -> JSONResponse:
    """Hard-delete a preference by ID."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            pref = db.query(CategorizationPreference).filter(
                CategorizationPreference.id == preference_id,
                CategorizationPreference.user_id == user_id,
            ).first()
            if not pref:
                return JSONResponse({"error": "Preference not found"}, status_code=404)
            db.delete(pref)
            db.commit()
            return JSONResponse({"id": preference_id, "status": "deleted"})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Delete preference error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/transactions/review-queue")
async def get_review_queue(request: Request) -> JSONResponse:
    """Return transactions that need human review after processing.

    Surfaces MANUAL_REVIEW items and AI/manual categorizations that are
    materially large or recurring. Rule-assigned transactions stay out of
    this queue.
    """
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        bank_name = request.query_params.get("bank_name")
        since = request.query_params.get("since")

        if not bank_name or not since:
            return JSONResponse(
                {"error": "bank_name and since query parameters are required"},
                status_code=400,
            )

        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            return JSONResponse(
                {"error": f"Invalid since format: {since}. Use ISO 8601."},
                status_code=400,
            )

        db = SessionLocal()
        try:
            _auto_resolve_low_value_manual_reviews(
                db,
                user_id=user_id,
                bank_name=bank_name,
                created_since=since_dt,
            )
            txs = (
                db.query(Transaction)
                .filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                    Transaction.created_at >= since_dt,
                )
                .all()
            )

            if not txs:
                return JSONResponse({
                    "transactions": [],
                    "total_count": 0,
                    "total_absolute_value": 0,
                    "materiality_threshold": 0,
                    "manual_review_count": 0,
                })

            total_abs = sum(abs(float(tx.amount)) for tx in txs)
            threshold = total_abs * 0.015

            desc_counts: Counter[str] = Counter()
            for tx in txs:
                desc_counts[tx.description.strip().lower()] += 1

            review_items: List[Dict[str, Any]] = []
            for tx in txs:
                amt = abs(float(tx.amount))
                is_manual = tx.category == MANUAL_REVIEW
                is_conflict = tx.review_status == "conflict"
                if is_conflict and tx.review_category:
                    current_category = normalize_category(tx.category or "")
                    suggested_category = normalize_category(tx.review_category or "")
                    if (
                        current_category is not None
                        and suggested_category is not None
                        and current_category == suggested_category
                    ):
                        is_conflict = False
                is_rule_based = tx.category_source == "rule"
                is_high = (not is_rule_based) and amt >= threshold
                is_recurring = (
                    not is_rule_based
                    and desc_counts[tx.description.strip().lower()] >= 3
                    and _meets_recurring_review_floor(tx.amount)
                )

                if not (is_manual or is_conflict or is_high or is_recurring):
                    continue

                priority = (
                    "ai_conflict" if is_conflict
                    else "manual_review" if is_manual
                    else "high_amount" if is_high
                    else "recurring"
                )

                item: Dict[str, Any] = {
                    "id": str(tx.id),
                    "date": tx.date.isoformat() if tx.date else None,
                    "description": tx.description,
                    "merchant": tx.merchant,
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "category": tx.category,
                    "category_source": tx.category_source,
                    "bank_name": tx.bank_name,
                    "review_priority": priority,
                    "is_recurring": is_recurring,
                    "review_status": tx.review_status,
                    "review_category": tx.review_category,
                    "review_reason": tx.review_reason,
                }
                _add_conversion_fields(item, tx)
                review_items.append(item)

            priority_order = {"ai_conflict": 0, "manual_review": 1, "high_amount": 2, "recurring": 3}
            review_items.sort(
                key=lambda r: (
                    priority_order.get(r["review_priority"], 9),
                    -abs(r["amount"]),
                )
            )

            manual_count = sum(
                1 for r in review_items if r["review_priority"] == "manual_review"
            )
            conflict_count = sum(
                1 for r in review_items if r["review_priority"] == "ai_conflict"
            )

            return JSONResponse({
                "transactions": review_items,
                "total_count": len(review_items),
                "total_absolute_value": round(total_abs, 2),
                "materiality_threshold": round(threshold, 2),
                "manual_review_count": manual_count,
                "conflict_count": conflict_count,
            })
        finally:
            db.close()

    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Review queue error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/transactions/manual-review")
async def get_manual_review_transactions(request: Request) -> JSONResponse:
    """List transactions needing manual review."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            bank_name = request.query_params.get("bank_name")

            query = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.category == MANUAL_REVIEW,
            )

            if bank_name:
                query = query.filter(Transaction.bank_name == bank_name)

            limit = int(request.query_params.get("limit", "100"))
            offset = int(request.query_params.get("offset", "0"))

            total = query.count()
            transactions = query.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()
            result = []
            for tx in transactions:
                entry = {
                    "id": str(tx.id),
                    "date": tx.date.isoformat() if tx.date else None,
                    "description": tx.description,
                    "merchant": tx.merchant,
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "category": tx.category,
                    "bank_name": tx.bank_name,
                    "profile": tx.profile,
                }
                _add_conversion_fields(entry, tx)
                result.append(entry)
            return JSONResponse({
                "transactions": result,
                "count": len(result),
                "total": total,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get manual review transactions error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/transactions/manual-review/categorize")
async def categorize_manual_review(request: Request) -> JSONResponse:
    """Categorize a MANUAL_REVIEW transaction and optionally create a rule."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        tx_id = data.get("id")
        category = data.get("category")
        create_rule = data.get("create_rule", False)
        rule_pattern = data.get("rule_pattern")
        pattern_type = data.get("pattern_type", "regex")

        if not tx_id or not category:
            return JSONResponse({"error": "id and category are required"}, status_code=400)

        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(
                Transaction.id == tx_id,
                Transaction.user_id == user_id,
            ).first()
            if not tx:
                return JSONResponse({"error": "Transaction not found"}, status_code=404)

            try:
                normalized = _apply_manual_category_override(tx, category)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

            rule_created = False
            if create_rule and rule_pattern:
                new_pref = CategorizationPreference(
                    user_id=user_id,
                    name=f"manual:{rule_pattern[:40]}",
                    rule={
                        "description_pattern": rule_pattern,
                        "pattern_type": pattern_type,
                        "category": normalized,
                    },
                    bank_name=tx.bank_name if tx.bank_name != "Unknown" else None,
                    priority=10,
                    enabled=True,
                    preference_type="categorization",
                )
                db.add(new_pref)
                rule_created = True

            db.commit()
            return JSONResponse({
                "transaction_id": str(tx.id),
                "category": normalized,
                "rule_created": rule_created,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Manual review categorize error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/transactions/review-conflicts")
async def get_review_conflicts(request: Request) -> JSONResponse:
    """List transactions where the review agent disagreed with the categorizer."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            query = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.review_status == "conflict",
            )
            query = query.filter(
                or_(
                    Transaction.review_category.is_(None),
                    func.lower(func.trim(Transaction.category))
                    != func.lower(func.trim(Transaction.review_category)),
                )
            )
            bank_name = request.query_params.get("bank_name")
            if bank_name:
                query = query.filter(Transaction.bank_name == bank_name)

            limit = int(request.query_params.get("limit", "100"))
            offset = int(request.query_params.get("offset", "0"))
            total = query.count()
            transactions = query.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()

            result = []
            for tx in transactions:
                entry = {
                    "id": str(tx.id),
                    "date": tx.date.isoformat() if tx.date else None,
                    "description": tx.description,
                    "merchant": tx.merchant,
                    "amount": float(tx.amount),
                    "currency": tx.currency,
                    "category": tx.category,
                    "category_source": tx.category_source,
                    "bank_name": tx.bank_name,
                    "review_status": tx.review_status,
                    "review_category": tx.review_category,
                    "review_reason": tx.review_reason,
                }
                _add_conversion_fields(entry, tx)
                result.append(entry)

            return JSONResponse({
                "transactions": result,
                "count": len(result),
                "total": total,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get review conflicts error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/transactions/resolve-conflict")
async def resolve_conflict(request: Request) -> JSONResponse:
    """Resolve a review conflict by choosing a category."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        tx_id = data.get("id")
        chosen_category = data.get("chosen_category")
        create_rule = data.get("create_rule", False)
        rule_pattern = data.get("rule_pattern")

        if not tx_id or not chosen_category:
            return JSONResponse(
                {"error": "id and chosen_category are required"}, status_code=400
            )

        db = SessionLocal()
        try:
            tx = db.query(Transaction).filter(
                Transaction.id == tx_id,
                Transaction.user_id == user_id,
            ).first()
            if not tx:
                return JSONResponse({"error": "Transaction not found"}, status_code=404)

            try:
                normalized = _apply_manual_category_override(tx, chosen_category)
            except ValueError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)

            rule_created = False
            if create_rule and rule_pattern:
                new_pref = CategorizationPreference(
                    user_id=user_id,
                    name=f"conflict-resolve:{rule_pattern[:40]}",
                    rule={
                        "description_pattern": rule_pattern,
                        "category": normalized,
                    },
                    bank_name=tx.bank_name if tx.bank_name != "Unknown" else None,
                    priority=10,
                    enabled=True,
                    preference_type="categorization",
                )
                db.add(new_pref)
                rule_created = True

            db.commit()
            return JSONResponse({
                "transaction_id": str(tx.id),
                "category": normalized,
                "review_status": "resolved",
                "rule_created": rule_created,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Resolve conflict error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/preferences/cleanup-rules")
async def cleanup_bad_rules(request: Request) -> JSONResponse:
    """Delete auto-generated rules that match card-number-style garbage patterns."""
    import re
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            prefs = db.query(CategorizationPreference).filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == "categorization",
            ).all()

            card_pattern = re.compile(r"^\w{2,4}\.?\s*\w{2}\s*\d{4,6}\*{4,6}\d{2,4}", re.IGNORECASE)
            deleted = 0
            for pref in prefs:
                if not isinstance(pref.rule, dict):
                    continue
                mp = pref.rule.get("merchant_pattern") or pref.rule.get("pattern") or ""
                if card_pattern.match(mp):
                    db.delete(pref)
                    deleted += 1

            db.commit()
            return JSONResponse({"deleted": deleted, "status": "ok"})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Cleanup rules error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/rules/analyze")
async def start_rule_analysis(request: Request) -> JSONResponse:
    """Start a background rule-analysis run."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        try:
            data = await request.json()
        except Exception:
            data = {}

        since_raw = data.get("since")
        scope_since = RULE_ANALYSIS_ALL_HISTORY_SINCE
        if since_raw:
            try:
                scope_since = date.fromisoformat(str(since_raw))
            except ValueError:
                return JSONResponse(
                    {"error": f"Invalid since date: {since_raw}. Use YYYY-MM-DD"},
                    status_code=400,
                )

        db = SessionLocal()
        try:
            run = RuleAnalysisRun(
                user_id=user_id,
                status="queued",
                scope_since=scope_since,
                summary_json=None,
            )
            db.add(run)
            db.commit()
            db.refresh(run)
        finally:
            db.close()

        run_id = str(run.id)
        with _rule_analysis_event_lock:
            _rule_analysis_event_logs[run_id] = []

        _rule_analysis_emit_event(run_id, {
            "type": "analysis_stage",
            "stage": "queued",
            "scope_since": scope_since.isoformat(),
        })

        threading.Thread(
            target=_run_rule_analysis_background,
            args=(run_id, user_id, scope_since),
            daemon=True,
        ).start()

        return JSONResponse({
            "run_id": run_id,
            "status": "queued",
            "scope_since": scope_since.isoformat(),
        })
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Start rule analysis error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/rules/analyze/latest")
async def get_latest_rule_analysis_run(request: Request) -> JSONResponse:
    """Return the most recent rule-analysis run for the current user."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            run = db.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.user_id == user_id,
            ).order_by(RuleAnalysisRun.created_at.desc()).first()
            if not run:
                return JSONResponse({"run": None})

            open_findings = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.run_id == run.id,
                RuleAnalysisFinding.status == "open",
            ).count()
            return JSONResponse({
                "run": {
                    "id": str(run.id),
                    "status": run.status,
                    "scope_since": run.scope_since.isoformat() if run.scope_since else None,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "summary": run.summary_json or {},
                    "error_message": run.error_message,
                    "open_findings": open_findings,
                }
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get latest rule analysis run error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/rules/analyze/{run_id}")
async def get_rule_analysis_run_status(request: Request, run_id: str) -> JSONResponse:
    """Return status and summary for a rule-analysis run."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            run = db.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.id == run_id,
                RuleAnalysisRun.user_id == user_id,
            ).first()
            if not run:
                return JSONResponse({"error": "Rule analysis run not found"}, status_code=404)

            findings = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.run_id == run.id,
            ).all()
            total_findings = len(findings)
            open_findings = sum(1 for finding in findings if finding.status == "open")
            type_counts = dict(Counter(finding.finding_type for finding in findings))

            return JSONResponse({
                "id": str(run.id),
                "status": run.status,
                "scope_since": run.scope_since.isoformat() if run.scope_since else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "summary": run.summary_json or {},
                "error_message": run.error_message,
                "total_findings": total_findings,
                "open_findings": open_findings,
                "type_counts": type_counts,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get rule analysis run status error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/rules/analyze/{run_id}/events")
async def stream_rule_analysis_events(request: Request, run_id: str):
    """SSE stream for rule-analysis progress events."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            run = db.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.id == run_id,
                RuleAnalysisRun.user_id == user_id,
            ).first()
            if not run:
                return JSONResponse({"error": "Rule analysis run not found"}, status_code=404)
        finally:
            db.close()

        async def event_generator():
            index = 0
            while True:
                with _rule_analysis_event_lock:
                    events = list(_rule_analysis_event_logs.get(run_id, []))
                while index < len(events):
                    yield f"data: {json.dumps(events[index])}\n\n"
                    index += 1

                db_status = SessionLocal()
                try:
                    run_status = db_status.query(RuleAnalysisRun).filter(
                        RuleAnalysisRun.id == run_id,
                        RuleAnalysisRun.user_id == user_id,
                    ).first()
                    status_value = run_status.status if run_status else "failed"
                finally:
                    db_status.close()

                if status_value in ("completed", "failed", "cancelled"):
                    with _rule_analysis_event_lock:
                        latest_events = _rule_analysis_event_logs.get(run_id, [])
                    if index >= len(latest_events):
                        break
                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Stream rule analysis events error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/rules/analyze/{run_id}/findings")
async def list_rule_analysis_findings(request: Request, run_id: str) -> JSONResponse:
    """List findings for a given rule-analysis run."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        status_filter = request.query_params.get("status")
        type_filter = request.query_params.get("type")
        limit = int(request.query_params.get("limit", "100"))
        offset = int(request.query_params.get("offset", "0"))

        db = SessionLocal()
        try:
            run = db.query(RuleAnalysisRun).filter(
                RuleAnalysisRun.id == run_id,
                RuleAnalysisRun.user_id == user_id,
            ).first()
            if not run:
                return JSONResponse({"error": "Rule analysis run not found"}, status_code=404)

            query = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.run_id == run_id,
                RuleAnalysisFinding.user_id == user_id,
            )
            if status_filter:
                query = query.filter(RuleAnalysisFinding.status == status_filter)
            if type_filter:
                query = query.filter(RuleAnalysisFinding.finding_type == type_filter)

            total = query.count()
            findings = query.order_by(
                RuleAnalysisFinding.created_at.desc()
            ).offset(offset).limit(limit).all()
            result = [{
                "id": str(finding.id),
                "run_id": str(finding.run_id),
                "finding_type": finding.finding_type,
                "status": finding.status,
                "confidence": float(finding.confidence),
                "bank_name": finding.bank_name,
                "payload": finding.payload_json if isinstance(finding.payload_json, dict) else {},
                "created_at": finding.created_at.isoformat() if finding.created_at else None,
                "resolved_at": finding.resolved_at.isoformat() if finding.resolved_at else None,
            } for finding in findings]

            return JSONResponse({
                "findings": result,
                "count": len(result),
                "total": total,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("List rule analysis findings error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/rules/analyze/findings/{finding_id}/apply")
async def apply_rule_analysis_finding(request: Request, finding_id: str) -> JSONResponse:
    """Apply a single open finding."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        raw_body = await request.body()
        data = {}
        if raw_body:
            try:
                data = json.loads(raw_body)
            except json.JSONDecodeError:
                return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
        chosen_category = data.get("chosen_category")
        db = SessionLocal()
        try:
            finding = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.id == finding_id,
                RuleAnalysisFinding.user_id == user_id,
            ).first()
            if not finding:
                return JSONResponse({"error": "Finding not found"}, status_code=404)
            if finding.status != "open":
                return JSONResponse({"error": "Finding is not open"}, status_code=400)

            action_result = _apply_rule_analysis_finding(
                db=db,
                user_id=user_id,
                finding=finding,
                chosen_category=chosen_category,
            )

            finding.status = "applied"
            finding.resolved_at = datetime.now(tz=timezone.utc)
            finding.updated_at = datetime.now(tz=timezone.utc)
            db.commit()

            return JSONResponse({
                "finding_id": str(finding.id),
                "status": finding.status,
                "result": action_result,
            })
        finally:
            db.close()
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Apply rule analysis finding error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/rules/analyze/findings/{finding_id}/dismiss")
async def dismiss_rule_analysis_finding(request: Request, finding_id: str) -> JSONResponse:
    """Dismiss a single open finding."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            finding = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.id == finding_id,
                RuleAnalysisFinding.user_id == user_id,
            ).first()
            if not finding:
                return JSONResponse({"error": "Finding not found"}, status_code=404)
            if finding.status != "open":
                return JSONResponse({"error": "Finding is not open"}, status_code=400)

            finding.status = "dismissed"
            finding.resolved_at = datetime.now(tz=timezone.utc)
            finding.updated_at = datetime.now(tz=timezone.utc)

            # For tx_conflict findings, mark the transaction as resolved so it
            # won't be re-flagged on the next analysis run.
            if finding.finding_type == FINDING_TX_CONFLICT:
                payload = finding.payload_json if isinstance(finding.payload_json, dict) else {}
                tx_id = payload.get("transaction_id")
                if tx_id:
                    tx = db.query(Transaction).filter(
                        Transaction.id == str(tx_id),
                        Transaction.user_id == user_id,
                    ).first()
                    if tx and tx.review_status != "resolved":
                        tx.review_status = "resolved"
                        tx.review_category = None
                        tx.review_reason = None
                        tx.updated_at = datetime.now(tz=timezone.utc)

            db.commit()

            return JSONResponse({
                "finding_id": str(finding.id),
                "status": finding.status,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Dismiss rule analysis finding error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/profiles")
async def get_profiles(request: Request) -> JSONResponse:
    """Return distinct profile names for the current user."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            rows = (
                db.query(Transaction.profile)
                .filter(
                    Transaction.user_id == user_id,
                    Transaction.profile.isnot(None),
                )
                .distinct()
                .all()
            )
            profiles = sorted(r[0] for r in rows if r[0])
            return JSONResponse({"profiles": profiles})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Get profiles error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/data-management/summary")
async def get_data_summary(request: Request) -> JSONResponse:
    """Return a summary of what data exists for the current user."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            dates = (
                db.query(Transaction.date)
                .filter(Transaction.user_id == user_id)
                .distinct()
                .all()
            )
            months = sorted(
                {d[0].strftime("%Y-%m") for d in dates if d[0]},
                reverse=True,
            )

            # Per-bank breakdown: bank → sorted months + tx count
            # Group by (bank_name, date) — portable across SQLite and PostgreSQL
            bank_date_rows = (
                db.query(Transaction.bank_name, Transaction.date, func.count(Transaction.id))
                .filter(Transaction.user_id == user_id)
                .group_by(Transaction.bank_name, Transaction.date)
                .all()
            )
            banks_map: Dict[str, Dict[str, Any]] = {}
            for bank, date_val, count in bank_date_rows:
                bank_key = bank or "Unknown"
                if bank_key not in banks_map:
                    banks_map[bank_key] = {"months": {}, "tx_count": 0}
                if date_val:
                    month_str = date_val.strftime("%Y-%m")
                    banks_map[bank_key]["months"][month_str] = (
                        banks_map[bank_key]["months"].get(month_str, 0) + count
                    )
                banks_map[bank_key]["tx_count"] += count

            banks_detail = [
                {
                    "bank": bank_key,
                    "months": sorted(months_map.keys(), reverse=True),
                    "tx_count": info["tx_count"],
                }
                for bank_key, info in sorted(banks_map.items())
                for months_map in [info["months"]]
            ]
            banks = sorted(banks_map.keys())

            tx_count = (
                db.query(Transaction)
                .filter(Transaction.user_id == user_id)
                .count()
            )

            cat_rules = (
                db.query(CategorizationPreference)
                .filter(
                    CategorizationPreference.user_id == user_id,
                    CategorizationPreference.preference_type == "categorization",
                )
                .count()
            )

            parsing_rules = (
                db.query(CategorizationPreference)
                .filter(
                    CategorizationPreference.user_id == user_id,
                    CategorizationPreference.preference_type == "parsing",
                )
                .count()
            )

            budget_count = (
                db.query(Budget)
                .filter(Budget.user_id == user_id)
                .count()
            )

            # Profiles breakdown
            profile_rows = (
                db.query(Transaction.profile, func.count(Transaction.id))
                .filter(Transaction.user_id == user_id, Transaction.profile.isnot(None))
                .group_by(Transaction.profile)
                .all()
            )
            profiles_detail = [
                {"profile": p, "tx_count": c}
                for p, c in sorted(profile_rows, key=lambda x: x[0] or "")
                if p
            ]

            return JSONResponse({
                "months": months,
                "banks": banks,
                "banks_detail": banks_detail,
                "profiles_detail": profiles_detail,
                "transaction_count": tx_count,
                "categorization_rules_count": cat_rules,
                "parsing_rules_count": parsing_rules,
                "budget_count": budget_count,
            })
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Data summary error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/data-management/transactions")
async def delete_transactions_bulk(request: Request) -> JSONResponse:
    """Delete transactions filtered by month and/or bank."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        month = data.get("month")
        bank_name = data.get("bank_name")

        if not month and not bank_name:
            return JSONResponse(
                {"error": "Provide at least one filter: month or bank_name"},
                status_code=400,
            )

        db = SessionLocal()
        try:
            query = db.query(Transaction).filter(Transaction.user_id == user_id)

            if month:
                try:
                    year, mon = month.split("-")
                    start = date(int(year), int(mon), 1)
                    if int(mon) == 12:
                        end = date(int(year) + 1, 1, 1)
                    else:
                        end = date(int(year), int(mon) + 1, 1)
                    query = query.filter(
                        Transaction.date >= start,
                        Transaction.date < end,
                    )
                except (ValueError, TypeError):
                    return JSONResponse(
                        {"error": f"Invalid month format: {month}. Use YYYY-MM"},
                        status_code=400,
                    )

            if bank_name:
                query = query.filter(Transaction.bank_name == bank_name)

            count = query.count()
            query.delete(synchronize_session=False)
            db.commit()

            return JSONResponse({"deleted": count, "status": "ok"})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Delete transactions error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/data-management/preferences")
async def delete_preferences_bulk(request: Request) -> JSONResponse:
    """Delete all preferences of a given type."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        preference_type = data.get("preference_type", "categorization")

        if preference_type not in ("categorization", "parsing"):
            return JSONResponse(
                {"error": "preference_type must be 'categorization' or 'parsing'"},
                status_code=400,
            )

        db = SessionLocal()
        try:
            query = db.query(CategorizationPreference).filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.preference_type == preference_type,
            )
            count = query.count()
            query.delete(synchronize_session=False)
            db.commit()

            return JSONResponse({"deleted": count, "status": "ok"})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Delete preferences error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/data-management/budgets")
async def delete_budgets_bulk(request: Request) -> JSONResponse:
    """Delete all budgets for the current user."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            query = db.query(Budget).filter(Budget.user_id == user_id)
            count = query.count()
            query.delete(synchronize_session=False)
            db.commit()

            return JSONResponse({"deleted": count, "status": "ok"})
        finally:
            db.close()
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    except Exception as e:
        logger.error("Delete budgets error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/categories")
async def get_categories(request: Request) -> JSONResponse:
    """Return predefined + user custom categories (excludes MANUAL_REVIEW)."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            custom_rows = (
                db.query(CustomCategory)
                .filter(CustomCategory.user_id == user_id)
                .order_by(CustomCategory.name)
                .all()
            )
            custom_names = [row.name for row in custom_rows]
            custom = [
                {"id": str(row.id), "name": row.name, "is_custom": True}
                for row in custom_rows
            ]
        finally:
            db.close()
        predefined = [
            {"id": None, "name": cat, "is_custom": False}
            for cat in PREDEFINED_CATEGORIES
        ]
        return JSONResponse({
            "categories": PREDEFINED_CATEGORIES + custom_names,
            "categories_detail": predefined + custom,
        })
    except Exception as e:
        logger.error("Get categories error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/categories")
async def create_custom_category(request: Request) -> JSONResponse:
    """Create a user-defined custom category."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        data = await request.json()
        name = str(data.get("name") or "").strip()
        if not name or len(name) > 100:
            return JSONResponse(
                {"error": "Category name is required and must be <=100 chars"},
                status_code=400,
            )
        for predefined in PREDEFINED_CATEGORIES:
            if name.lower() == predefined.lower():
                return JSONResponse(
                    {"error": f"'{name}' already exists as a built-in category"},
                    status_code=409,
                )
        db = SessionLocal()
        try:
            existing = (
                db.query(CustomCategory)
                .filter(
                    CustomCategory.user_id == user_id,
                    CustomCategory.name == name,
                )
                .first()
            )
            if existing:
                return JSONResponse(
                    {"error": f"Custom category '{name}' already exists"},
                    status_code=409,
                )
            cat = CustomCategory(user_id=user_id, name=name)
            db.add(cat)
            db.commit()
            db.refresh(cat)
            return JSONResponse({
                "id": str(cat.id),
                "name": cat.name,
                "is_custom": True,
            }, status_code=201)
        finally:
            db.close()
    except Exception as e:
        logger.error("Create custom category error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/categories/{category_id}")
async def delete_custom_category(request: Request, category_id: str) -> JSONResponse:
    """Delete a user-defined custom category."""
    try:
        user_id = await resolve_request_user_id(request, require_auth=True)
        db = SessionLocal()
        try:
            cat = (
                db.query(CustomCategory)
                .filter(
                    CustomCategory.id == category_id,
                    CustomCategory.user_id == user_id,
                )
                .first()
            )
            if not cat:
                return JSONResponse({"error": "Custom category not found"}, status_code=404)
            db.delete(cat)
            db.commit()
            return JSONResponse({"deleted": True, "id": category_id})
        finally:
            db.close()
    except Exception as e:
        logger.error("Delete custom category error", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/{full_path:path}", response_model=None)
async def spa_fallback(full_path: str):
    """Fallback to index.html for client-side routing."""
    if full_path.startswith("api") or full_path.startswith("static") or full_path == "health":
        return JSONResponse({"error": "Not found"}, status_code=404)
    if WEB_INDEX_PATH.exists():
        return HTMLResponse(WEB_INDEX_PATH.read_text(encoding="utf-8"))
    return JSONResponse({"error": "Not found"}, status_code=404)
