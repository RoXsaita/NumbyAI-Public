"""
Statement Analyzer - Analyze statement structure using heuristics + LLM fallback

This service analyzes bank statement CSV files using pattern matching and heuristics
to detect columns, date formats, currency, etc. Falls back to the LLM when
heuristic confidence is low.
"""
import csv
import io
import os
import pandas as pd
import re
from typing import Dict, Optional, List, Union, Tuple
from app.database import SessionLocal, CategorizationPreference
from app.logger import create_logger

logger = create_logger("statement_analyzer")

_DATE_PATTERNS: List[Tuple[str, str]] = [
    (r'^\d{4}-\d{2}-\d{2}', 'YYYY-MM-DD'),
    (r'^\d{2}-\d{2}-\d{4}$', 'DD-MM-YYYY'),
    (r'^\d{2}/\d{2}/\d{4}$', 'DD/MM/YYYY'),
    (r'^\d{2}/\d{2}/\d{4}$', 'MM/DD/YYYY'),
    (r'^\d{4}/\d{2}/\d{2}$', 'YYYY/MM/DD'),
    (r'^\d{1,2}\.\d{1,2}\.\d{4}$', 'DD.MM.YYYY'),
    (r'^\d{1,2}\s\w{3}\s\d{4}$', 'DD Mon YYYY'),
    (r'^\d{1,2}/\d{1,2}/\d{2}$', 'DD/MM/YY'),
    (r'^\d{1,2}-\d{1,2}-\d{2}$', 'DD-MM-YY'),
    (r'^\d{8}$', 'YYYYMMDD'),
]

_NUMERIC_RE = re.compile(r'^-?\d+[.,]?\d*$')
_CURRENCY_STRIP_RE = re.compile(r'[$€£¥zł₹₽₩₪₺₴₿CHF\s]', re.IGNORECASE)

_CURRENCY_SYMBOLS: Dict[str, str] = {
    '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', 'zł': 'PLN', '₹': 'INR',
    '₽': 'RUB', '₩': 'KRW', '₪': 'ILS', '₺': 'TRY', '₴': 'UAH', '₿': 'BTC',
    'CHF': 'CHF',
}

_CURRENCY_CODES: List[str] = [
    'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'CNY', 'HKD',
    'SGD', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'RON', 'BGN', 'HRK',
    'RUB', 'TRY', 'ZAR', 'BRL', 'MXN', 'INR', 'IDR', 'MYR', 'PHP', 'THB',
    'KRW', 'TWD', 'ILS', 'AED', 'SAR', 'EGP', 'NGN',
]


def detect_delimiter(file_path: str) -> str:
    """Auto-detect the CSV field delimiter using csv.Sniffer with a counting fallback.

    Reads up to 8 KB from the file.  Returns one of ``","`` ``";"`` ``"\\t"`` ``"|"``.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            sample = fh.read(8192)
    except Exception:
        return ","

    # csv.Sniffer works well when the file is reasonably regular
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        if dialect.delimiter in (',', ';', '\t', '|'):
            return dialect.delimiter
    except csv.Error:
        pass

    # Fallback: count candidate delimiters across the first 10 non-empty lines
    lines = [ln for ln in sample.splitlines() if ln.strip()][:10]
    if not lines:
        return ","

    candidates = {',': 0, ';': 0, '\t': 0, '|': 0}
    for line in lines:
        for ch in candidates:
            candidates[ch] += line.count(ch)

    best = max(candidates, key=lambda c: candidates[c])
    if candidates[best] == 0:
        return ","
    return best


def validate_column_reference(column_ref: Union[str, List[str]]) -> bool:
    """Validate that a column reference is a valid numeric index, not data."""
    if isinstance(column_ref, list):
        return all(validate_column_reference(ref) for ref in column_ref)

    if not column_ref or not isinstance(column_ref, str):
        return False

    try:
        idx = int(column_ref)
        if idx < 0 or idx > 100:
            return False
        if column_ref != str(idx):
            return False
    except (ValueError, TypeError):
        return False

    if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$', column_ref):
        return False
    if re.match(r'^\d+[.,]\d+$', column_ref):
        return False
    if len(column_ref) > 3:
        return False

    return True


def check_existing_parsing_preferences(bank_name: str, user_id: str) -> Optional[Dict]:
    """Check if parsing preferences exist for this bank."""
    db = SessionLocal()
    try:
        pref = db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.bank_name == bank_name,
            CategorizationPreference.preference_type == "parsing",
            CategorizationPreference.enabled.is_(True)
        ).first()

        if pref and pref.rule:
            logger.info("Found existing parsing preferences", {
                "bank_name": bank_name,
                "user_id": user_id
            })
            return pref.rule
        else:
            return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Column-level helpers
# ---------------------------------------------------------------------------

def _is_numeric_value(val: str) -> bool:
    """Return True if val looks like a numeric/currency amount (US, EU, Swiss, etc.)."""
    cleaned = _CURRENCY_STRIP_RE.sub('', val).replace('(', '').replace(')', '').replace("'", '')
    cleaned = cleaned.replace('\xa0', '').replace(' ', '').strip()
    if not cleaned:
        return False

    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            # EU: 1.234,56 -> 1234.56
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56 -> 1234.56
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts_after = cleaned.split(',')[-1]
        if len(parts_after) == 3 and parts_after.replace('-', '').isdigit():
            cleaned = cleaned.replace(',', '')  # US thousands: 1,234
        else:
            cleaned = cleaned.replace(',', '.')  # EU decimal: 123,45
    # dots-only: 1.234 could be thousands or decimal — accept either way

    return bool(_NUMERIC_RE.match(cleaned))


def _is_date_value(val: str) -> bool:
    """Return True if val matches any known date pattern."""
    val = val.strip()
    if not val:
        return False
    for pattern, _ in _DATE_PATTERNS:
        if re.match(pattern, val):
            return True
    return False


def _col_stats(df: pd.DataFrame, col_idx: int, sample_n: int = 20) -> Dict:
    """Compute lightweight statistics for a single column."""
    col_data = df.iloc[:, col_idx].astype(str).str.strip()
    non_empty = col_data[col_data != '']
    sample = non_empty.head(sample_n)
    total = len(sample)
    if total == 0:
        return {"total": 0, "empty_pct": 1.0, "numeric": 0, "date": 0, "avg_len": 0.0, "non_empty": 0}
    date_count = sum(1 for v in sample if _is_date_value(v))
    numeric_count = sum(1 for v in sample if _is_numeric_value(v))
    avg_len = sum(len(str(v)) for v in sample) / total
    empty_pct = 1 - (len(non_empty) / max(len(col_data), 1))
    return {
        "total": total,
        "empty_pct": empty_pct,
        "numeric": numeric_count,
        "date": date_count,
        "avg_len": avg_len,
        "non_empty": len(non_empty),
    }


# ---------------------------------------------------------------------------
# First transaction row detection
# ---------------------------------------------------------------------------

def _detect_first_transaction_row(df_raw: pd.DataFrame) -> int:
    """
    Scan from the top to find the first row that looks like transaction data.
    Returns 1-indexed row number (file row, not 0-based DataFrame index).
    """
    for row_idx in range(len(df_raw)):
        row_vals = df_raw.iloc[row_idx].astype(str).str.strip().tolist()
        has_date = any(_is_date_value(v) for v in row_vals)
        has_numeric = any(_is_numeric_value(v) for v in row_vals)
        if has_date and has_numeric:
            return row_idx + 1
    return 1


# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

def _detect_date_column(df: pd.DataFrame, max_cols: int = None) -> Tuple[Optional[str], Optional[str], str]:
    """Detect date column and format. Returns (date_column, date_format, confidence)."""
    if max_cols is None:
        max_cols = len(df.columns)
    best_col = None
    best_format = None
    best_score = 0

    for col_idx in range(min(max_cols, len(df.columns))):
        col_data = df.iloc[:, col_idx].astype(str).str.strip()
        col_data = col_data[col_data != '']
        if len(col_data) < 2:
            continue
        sample = col_data.head(20)
        for pattern, fmt in _DATE_PATTERNS:
            matches = sum(1 for val in sample if re.match(pattern, str(val)))
            score = matches / len(sample)
            if score > best_score:
                best_score = score
                best_col = str(col_idx)
                best_format = fmt

    if best_score >= 0.6:
        confidence = "high" if best_score >= 0.85 else "medium"
        return (best_col, best_format, confidence)
    return (None, None, "low")


# ---------------------------------------------------------------------------
# Amount / inflow-outflow detection
# ---------------------------------------------------------------------------

def _score_numeric_column(df: pd.DataFrame, col_idx: int, sample_n: int = 20) -> float:
    """Return the fraction of non-empty sample values that parse as numbers."""
    col_data = df.iloc[:, col_idx].astype(str).str.strip()
    non_empty = col_data[col_data != '']
    sample = non_empty.head(sample_n)
    if len(sample) < 2:
        return 0.0
    return sum(1 for v in sample if _is_numeric_value(v)) / len(sample)


def _has_any_numeric(df: pd.DataFrame, col_idx: int) -> bool:
    """Return True if the column has at least one numeric-looking value."""
    col_data = df.iloc[:, col_idx].astype(str).str.strip()
    return any(_is_numeric_value(v) for v in col_data.head(20) if v)


def _detect_amount_columns(
    df: pd.DataFrame,
    exclude_cols: List[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Detect amount column(s).
    Returns (amount_col, inflow_col, outflow_col, confidence).
    If inflow/outflow pair is detected, amount_col is None.
    """
    numeric_cols: List[Tuple[int, float]] = []
    for col_idx in range(len(df.columns)):
        if str(col_idx) in exclude_cols:
            continue
        score = _score_numeric_column(df, col_idx)
        if score >= 0.5:
            numeric_cols.append((col_idx, score))

    if not numeric_cols:
        return (None, None, None, "low")

    # Check for inflow/outflow pair: look for adjacent columns where one has
    # high numeric score and the neighbor has at least some numeric values,
    # and the two are complementary (one empty when the other isn't).
    for col_a_idx, a_score in numeric_cols:
        for offset in [1, 2]:
            col_b_idx = col_a_idx + offset
            if col_b_idx >= len(df.columns):
                continue
            if str(col_b_idx) in exclude_cols:
                continue
            if not _has_any_numeric(df, col_b_idx):
                continue

            a_data = df.iloc[:, col_a_idx].astype(str).str.strip()
            b_data = df.iloc[:, col_b_idx].astype(str).str.strip()
            sample_len = min(20, len(df))
            complementary = 0
            for r in range(sample_len):
                a_val = a_data.iloc[r] if r < len(a_data) else ''
                b_val = b_data.iloc[r] if r < len(b_data) else ''
                a_empty = (a_val == '' or a_val == '0' or a_val == '0.00')
                b_empty = (b_val == '' or b_val == '0' or b_val == '0.00')
                if a_empty != b_empty:
                    complementary += 1
            if sample_len > 0 and complementary / sample_len >= 0.6:
                return (None, str(col_a_idx), str(col_b_idx), "high")

    # Single amount column: pick the one with the highest numeric score
    best = max(numeric_cols, key=lambda x: x[1])
    confidence = "high" if best[1] >= 0.85 else "medium"
    return (str(best[0]), None, None, confidence)


# ---------------------------------------------------------------------------
# Description / vendor detection
# ---------------------------------------------------------------------------

def _detect_text_columns(
    df: pd.DataFrame,
    exclude_cols: List[str],
    min_avg_len: float = 3.0,
) -> List[Tuple[int, float]]:
    """Return text columns sorted by avg length descending, excluding known columns."""
    results: List[Tuple[int, float]] = []
    for col_idx in range(len(df.columns)):
        if str(col_idx) in exclude_cols:
            continue
        stats = _col_stats(df, col_idx)
        if stats["total"] < 2:
            continue
        if stats["numeric"] / max(stats["total"], 1) >= 0.7:
            continue
        if stats["date"] / max(stats["total"], 1) >= 0.5:
            continue
        if stats["avg_len"] < min_avg_len:
            continue
        results.append((col_idx, stats["avg_len"]))
    results.sort(key=lambda x: -x[1])
    return results


def _detect_description_and_vendor(
    df: pd.DataFrame,
    exclude_cols: List[str],
) -> Tuple[List[str], Optional[str], Dict[str, str]]:
    """
    Detect description column(s) and vendor/payee column.
    Returns (description_cols, vendor_col, confidence_map).
    """
    text_cols = _detect_text_columns(df, exclude_cols)
    if not text_cols:
        return ([], None, {})

    description_cols: List[str] = []
    vendor_col: Optional[str] = None
    confidence: Dict[str, str] = {}

    # The longest text column is the primary description
    primary = text_cols[0]
    description_cols.append(str(primary[0]))
    confidence["description"] = "high" if primary[1] > 15 else "medium"

    # Classify remaining text columns
    for col_idx, avg_len in text_cols[1:]:
        if 3 <= avg_len <= 40 and vendor_col is None:
            vendor_col = str(col_idx)
            confidence["vendor_payee"] = "medium"
        elif avg_len > 8:
            description_cols.append(str(col_idx))

    return (description_cols, vendor_col, confidence)


# ---------------------------------------------------------------------------
# Balance detection
# ---------------------------------------------------------------------------

def _detect_balance_column(
    df: pd.DataFrame,
    amount_col: Optional[str],
    inflow_col: Optional[str],
    outflow_col: Optional[str],
    exclude_cols: List[str],
) -> Tuple[Optional[str], str]:
    """Detect balance column. Returns (balance_col, confidence)."""
    ref_col = amount_col or outflow_col or inflow_col
    if not ref_col:
        return (None, "low")

    ref_idx = int(ref_col)
    candidates: List[Tuple[int, float]] = []
    for col_idx in range(len(df.columns)):
        if str(col_idx) in exclude_cols:
            continue
        if abs(col_idx - ref_idx) > 4:
            continue
        score = _score_numeric_column(df, col_idx)
        if score >= 0.7:
            col_data = df.iloc[:, col_idx].astype(str).str.strip()
            non_empty = col_data[col_data != '']
            sample = non_empty.head(20)
            all_positive = all(
                not v.strip().startswith('-') and not v.strip().startswith('(')
                for v in sample if _is_numeric_value(v)
            )
            if all_positive and len(sample) >= 3:
                candidates.append((col_idx, score))

    if not candidates:
        return (None, "low")
    best = max(candidates, key=lambda x: x[1])
    return (str(best[0]), "medium")


# ---------------------------------------------------------------------------
# Currency detection
# ---------------------------------------------------------------------------

def _detect_currency(
    df_raw: pd.DataFrame,
    amount_col: Optional[str],
    inflow_col: Optional[str],
    outflow_col: Optional[str],
) -> Tuple[str, str]:
    """Detect currency from symbols in data and headers. Returns (code, confidence)."""
    # Gather text to scan: amount columns + all header/first rows
    scan_texts: List[str] = []

    # Scan all cells in first 2 rows (may contain header text like "Amount (EUR)")
    for row_idx in range(min(2, len(df_raw))):
        for col_idx in range(len(df_raw.columns)):
            scan_texts.append(str(df_raw.iloc[row_idx, col_idx]))

    # Scan amount column values
    for col_ref in [amount_col, inflow_col, outflow_col]:
        if col_ref is not None:
            col_data = df_raw.iloc[:, int(col_ref)].astype(str).str.strip()
            scan_texts.extend(col_data.head(10).tolist())

    combined = ' '.join(scan_texts)

    # Check symbols
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in combined:
            return (code, "high")

    # Check ISO codes (word boundary)
    combined_upper = combined.upper()
    for code in _CURRENCY_CODES:
        if re.search(r'\b' + code + r'\b', combined_upper):
            return (code, "medium")

    return ("USD", "low")


# ---------------------------------------------------------------------------
# Number format detection (EU vs US)
# ---------------------------------------------------------------------------

def _detect_number_format(
    df: pd.DataFrame,
    amount_col: Optional[str],
    inflow_col: Optional[str],
    outflow_col: Optional[str],
) -> str:
    """
    Determine whether amounts use US (1,234.56) or EU (1.234,56) formatting.
    Returns "us", "eu", or "auto" if indeterminate.
    """
    cols_to_check = [c for c in [amount_col, inflow_col, outflow_col] if c is not None]
    if not cols_to_check:
        return "auto"

    eu_signals = 0
    us_signals = 0
    for col_ref in cols_to_check:
        col_data = df.iloc[:, int(col_ref)].astype(str).str.strip()
        non_empty = col_data[col_data != '']
        for val in non_empty.head(30):
            v = _CURRENCY_STRIP_RE.sub('', str(val)).replace('(', '').replace(')', '').replace("'", '').strip()
            if not v:
                continue
            # Both separators present → rightmost determines
            if ',' in v and '.' in v:
                if v.rfind(',') > v.rfind('.'):
                    eu_signals += 1
                else:
                    us_signals += 1
            elif ',' in v:
                parts_after_comma = v.split(',')[-1]
                if len(parts_after_comma) == 2:
                    eu_signals += 1
                elif len(parts_after_comma) == 3 and parts_after_comma.isdigit():
                    us_signals += 1

    if eu_signals > 0 and us_signals == 0:
        return "eu"
    if us_signals > 0 and eu_signals == 0:
        return "us"
    if eu_signals > us_signals:
        return "eu"
    if us_signals > eu_signals:
        return "us"
    return "auto"


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

_LLM_RESPONSE_SCHEMA: Dict = {
    "type": "object",
    "properties": {
        "columns_found": {"type": "array", "items": {"type": "string"}},
        "date_column": {"type": "string"},
        "description_column": {"type": "string"},
        "amount_column": {"type": "string"},
        "balance_column": {"type": ["string", "null"]},
        "date_format": {"type": "string"},
        "currency": {"type": "string"},
        "has_headers": {"type": "boolean"},
        "skip_rows": {"type": "integer"},
        "amount_positive_is": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string"},
    },
    "required": ["date_column", "description_column", "amount_column"],
}


def _try_llm_fallback(
    file_path: str,
    df_raw: pd.DataFrame,
    heuristic_mappings: Dict,
    confidence_map: Dict[str, str],
) -> Dict:
    """
    Call the LLM to fill gaps when heuristic confidence is low.
    Returns an updated ``suggested_mappings`` dict; heuristic results win when confident.
    """
    try:
        from app.services.llm_service import call_llm_json_object, get_llm_status

        status = get_llm_status()
        if not status.get("available"):
            logger.info("LLM not available for fallback, using heuristics only")
            return heuristic_mappings

        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "prompts", "analyze_statement_structure.txt"
        )
        with open(prompt_path) as f:
            prompt_template = f.read()

        # Build CSV sample from raw data (first 15 rows)
        sample_rows = df_raw.head(15)
        csv_sample = sample_rows.to_csv(index=False, header=False)
        prompt = prompt_template.replace("{{csv_sample}}", csv_sample)

        llm_result = call_llm_json_object(prompt, _LLM_RESPONSE_SCHEMA)
        logger.info("LLM fallback returned", {"llm_result_keys": list(llm_result.keys())})

        # Merge: only fill fields where heuristic confidence is "low" or missing
        merged = dict(heuristic_mappings)
        merged_col_mappings = dict(merged.get("column_mappings", {}))

        field_to_llm_key = {
            "date": "date_column",
            "description": "description_column",
            "amount": "amount_column",
            "balance": "balance_column",
        }

        for field_type, llm_key in field_to_llm_key.items():
            if confidence_map.get(field_type) in ("high", "medium"):
                continue
            llm_val = llm_result.get(llm_key)
            if llm_val and str(llm_val).strip():
                col_ref = str(llm_val).strip()
                try:
                    int(col_ref)
                except ValueError:
                    continue
                has_existing = any(v == field_type for v in merged_col_mappings.values())
                if not has_existing:
                    merged_col_mappings[col_ref] = field_type
                    confidence_map[field_type] = "medium"

        merged["column_mappings"] = merged_col_mappings

        if llm_result.get("date_format") and confidence_map.get("date") != "high":
            merged["date_format"] = llm_result["date_format"]
        if llm_result.get("currency") and confidence_map.get("currency") != "high":
            merged["currency"] = llm_result["currency"]
        if llm_result.get("skip_rows") is not None:
            first_tx = int(llm_result["skip_rows"]) + 1
            if first_tx > 0:
                merged["first_transaction_row"] = first_tx

        merged["confidence"] = confidence_map
        return merged

    except Exception as e:
        logger.warn("LLM fallback failed, using heuristics only", {"error": str(e)})
        return heuristic_mappings


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_statement_structure_from_file(file_path: str, user_id: str) -> Dict:
    """
    Analyze statement structure using enhanced heuristics.

    Returns a dict with the legacy ``analysis`` fields **and** a new
    ``suggested_mappings`` dict that the frontend can use to pre-populate
    column mapping dropdowns.
    """
    try:
        delimiter = ","
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            df_raw = pd.read_excel(file_path, nrows=50, dtype=str, keep_default_na=False, header=None)
        else:
            delimiter = detect_delimiter(file_path)
            try:
                df_raw = pd.read_csv(
                    file_path, nrows=50, dtype=str, keep_default_na=False, header=None,
                    sep=delimiter,
                )
            except pd.errors.ParserError:
                df_raw = pd.read_csv(
                    file_path, nrows=50, dtype=str, keep_default_na=False, header=None,
                    on_bad_lines='skip', sep=delimiter,
                )

        columns_found = [str(i) for i in range(len(df_raw.columns))]
        first_tx_row = _detect_first_transaction_row(df_raw)

        # Build a DataFrame starting from the first transaction row for column detection
        df = df_raw.iloc[first_tx_row - 1:].reset_index(drop=True)
        if len(df) < 2:
            df = df_raw

        # --- Detect columns ---
        date_column, date_format, date_conf = _detect_date_column(df)
        exclude = [c for c in [date_column] if c]

        amount_col, inflow_col, outflow_col, amount_conf = _detect_amount_columns(df, exclude)
        for c in [amount_col, inflow_col, outflow_col]:
            if c:
                exclude.append(c)

        desc_cols, vendor_col, text_conf = _detect_description_and_vendor(df, exclude)
        for c in desc_cols:
            exclude.append(c)
        if vendor_col:
            exclude.append(vendor_col)

        balance_col, balance_conf = _detect_balance_column(
            df, amount_col, inflow_col, outflow_col, exclude,
        )

        currency, currency_conf = _detect_currency(df_raw, amount_col, inflow_col, outflow_col)
        number_format = _detect_number_format(df, amount_col, inflow_col, outflow_col)

        # --- Build confidence map ---
        confidence_map: Dict[str, str] = {}
        confidence_map["date"] = date_conf
        if amount_col:
            confidence_map["amount"] = amount_conf
        if inflow_col:
            confidence_map["inflow"] = amount_conf
        if outflow_col:
            confidence_map["outflow"] = amount_conf
        confidence_map.update(text_conf)
        if balance_col:
            confidence_map["balance"] = balance_conf
        confidence_map["currency"] = currency_conf

        # Overall confidence
        required_found = bool(date_column) and bool(desc_cols) and bool(amount_col or inflow_col)
        overall = "high" if required_found and all(
            v in ("high", "medium") for v in confidence_map.values()
        ) else ("medium" if required_found else "low")

        # --- Build suggested_mappings (frontend-friendly: colIdx -> fieldType) ---
        col_mappings: Dict[str, str] = {}
        if date_column is not None:
            col_mappings[date_column] = "date"
        if amount_col is not None:
            col_mappings[amount_col] = "amount"
        if inflow_col is not None:
            col_mappings[inflow_col] = "inflow"
        if outflow_col is not None:
            col_mappings[outflow_col] = "outflow"
        for dc in desc_cols:
            col_mappings[dc] = "description"
        if vendor_col is not None:
            col_mappings[vendor_col] = "vendor_payee"
        if balance_col is not None:
            col_mappings[balance_col] = "balance"

        suggested_mappings: Dict = {
            "column_mappings": col_mappings,
            "first_transaction_row": first_tx_row,
            "date_format": date_format or "DD/MM/YYYY",
            "currency": currency,
            "number_format": number_format,
            "delimiter": delimiter,
            "confidence": confidence_map,
        }

        # --- LLM fallback for low-confidence heuristics ---
        if overall == "low":
            suggested_mappings = _try_llm_fallback(
                file_path, df_raw, suggested_mappings, confidence_map,
            )

        # --- Legacy analysis dict (kept for backward compatibility) ---
        has_headers = first_tx_row > 1
        analysis = {
            "columns_found": columns_found,
            "date_column": date_column or "0",
            "description_column": desc_cols[0] if desc_cols else "1",
            "amount_column": amount_col or (inflow_col if inflow_col else "2"),
            "balance_column": balance_col,
            "date_format": date_format or "DD/MM/YYYY",
            "currency": currency,
            "has_headers": has_headers,
            "skip_rows": max(0, first_tx_row - 1),
            "amount_positive_is": "debit",
            "questions": [],
            "confidence": overall,
            "suggested_mappings": suggested_mappings,
        }

        logger.info("Statement structure analyzed (enhanced heuristics)", {
            "file_path": file_path,
            "delimiter": delimiter,
            "first_tx_row": first_tx_row,
            "date_column": date_column,
            "amount_col": amount_col,
            "inflow_col": inflow_col,
            "outflow_col": outflow_col,
            "description_cols": desc_cols,
            "vendor_col": vendor_col,
            "balance_col": balance_col,
            "currency": currency,
            "number_format": number_format,
            "confidence": overall,
        })

        return analysis

    except Exception as e:
        logger.error("Failed to analyze statement structure", {
            "file_path": file_path,
            "error": str(e)
        })
        raise


def build_parsing_schema(analysis: Dict, user_responses: Dict) -> Dict:
    """
    Build parsing schema from heuristic analysis and user responses.
    
    Args:
        analysis: Heuristic analysis dict with detected structure
        user_responses: User answers to questions (dict with question -> answer)
    
    Returns:
        Unified parsing schema dict
    """
    suggested = analysis.get("suggested_mappings", {})
    schema = {
        "column_mappings": {
            "date": analysis.get("date_column", ""),
            "description": analysis.get("description_column", ""),
            "amount": analysis.get("amount_column", ""),
        },
        "date_format": analysis.get("date_format", "MM/DD/YYYY"),
        "currency": analysis.get("currency", "USD"),
        "has_headers": analysis.get("has_headers", True),
        "skip_rows": analysis.get("skip_rows", 0),
        "amount_positive_is": analysis.get("amount_positive_is", "debit"),
        "delimiter": suggested.get("delimiter", ","),
        "number_format": suggested.get("number_format", "auto"),
    }
    
    # Add balance column if detected
    if analysis.get("balance_column"):
        schema["column_mappings"]["balance"] = analysis["balance_column"]
    
    # Override with user responses
    if "date_column" in user_responses:
        schema["column_mappings"]["date"] = user_responses["date_column"]
    if "description_column" in user_responses:
        schema["column_mappings"]["description"] = user_responses["description_column"]
    if "amount_column" in user_responses:
        schema["column_mappings"]["amount"] = user_responses["amount_column"]
    if "balance_column" in user_responses:
        schema["column_mappings"]["balance"] = user_responses["balance_column"]
    if "date_format" in user_responses:
        schema["date_format"] = user_responses["date_format"]
    if "currency" in user_responses:
        schema["currency"] = user_responses["currency"]
    if "has_headers" in user_responses:
        schema["has_headers"] = user_responses["has_headers"]
    if "skip_rows" in user_responses:
        schema["skip_rows"] = int(user_responses["skip_rows"])
    if "amount_positive_is" in user_responses:
        schema["amount_positive_is"] = user_responses["amount_positive_is"]
    
    return schema


def save_parsing_schema(schema: Dict, bank_name: str, user_id: str, file_format: str = "csv") -> None:
    """
    Save parsing schema as CategorizationPreference for future use.
    
    Args:
        schema: Parsing schema dict
        bank_name: Bank name
        user_id: User ID
        file_format: File format (csv, xlsx, etc.)
    """
    # Validate column_mappings before saving
    column_mappings = schema.get('column_mappings', {})
    if column_mappings:
        invalid_refs = []
        for field_type, column_ref in column_mappings.items():
            if not validate_column_reference(column_ref):
                invalid_refs.append(f"{field_type}: {column_ref}")
        
        if invalid_refs:
            error_msg = (
                f"Invalid column mappings detected for bank '{bank_name}'. "
                f"The following fields contain data values instead of column indices: {', '.join(invalid_refs)}. "
                f"Column references must be numeric indices like '0', '1', '2'."
            )
            logger.error("Validation failed - refusing to save corrupted mappings", {
                "bank_name": bank_name,
                "user_id": user_id,
                "invalid_refs": invalid_refs,
                "column_mappings": column_mappings
            })
            raise ValueError(error_msg)
    
    logger.info("Column mappings validated successfully", {
        "bank_name": bank_name,
        "column_mappings": column_mappings
    })
    
    db = SessionLocal()
    try:
        # Check if preference already exists
        existing = db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id,
            CategorizationPreference.bank_name == bank_name,
            CategorizationPreference.preference_type == "parsing",
            CategorizationPreference.name == f"parsing_{bank_name}_{file_format}"
        ).first()
        
        if existing:
            # Update existing
            existing.rule = schema
            from datetime import datetime, timezone
            existing.updated_at = datetime.now(timezone.utc)
            logger.info("Updated parsing preferences", {
                "bank_name": bank_name,
                "user_id": user_id
            })
        else:
            # Create new
            pref = CategorizationPreference(
                user_id=user_id,
                bank_name=bank_name,
                name=f"parsing_{bank_name}_{file_format}",
                rule=schema,
                preference_type="parsing",
                enabled=True,
                priority=0
            )
            db.add(pref)
            logger.info("Saved new parsing preferences", {
                "bank_name": bank_name,
                "user_id": user_id
            })
        
        db.commit()
        
    finally:
        db.close()
