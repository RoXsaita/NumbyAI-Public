"""
Statement Parser - CSV/Excel parsing and transaction extraction

This module handles parsing of bank statement files (CSV/Excel) and extracting
transaction data. It applies parsing schemas (from CategorizationPreference)
to normalize transaction data.
"""
import pandas as pd
import re
from typing import Dict, List, Optional
from datetime import date, datetime
from decimal import Decimal
from app.logger import create_logger

logger = create_logger("statement_parser")


def _has_column_mapping(column_ref: object) -> bool:
    """Return True when a schema column mapping is explicitly configured."""
    if column_ref is None:
        return False
    if isinstance(column_ref, str):
        return bool(column_ref.strip())
    return True


def parse_csv_statement(file_path: str, schema: Dict) -> List[Dict]:
    """
    Parse CSV/Excel statement using provided schema.
    
    Args:
        file_path: Path to CSV/Excel file
        schema: Parsing schema with column mappings, date format, etc.
                Expected keys:
                - column_mappings: {date: "Column A", description: "Column B", amount: "Column C", ...}
                - date_format: "MM/DD/YYYY" or similar
                - currency: "USD" or similar
                - has_headers: bool
                - skip_rows: int (0-indexed, number of rows to skip)
                - first_transaction_row: int (1-indexed, user-friendly row number of first transaction)
                - amount_positive_is: "debit" or "credit"
    
    Returns:
        List of raw transaction dicts with: date, description, amount, balance (if available)
    """
    try:
        # Calculate skip_rows from first_transaction_row
        # first_transaction_row is 1-indexed (user-friendly)
        # skip_rows is 0-indexed (number of rows to skip before reading)
        skip_rows = 0
        if 'first_transaction_row' in schema and schema.get('first_transaction_row'):
            first_row = int(schema['first_transaction_row'])
            # Skip all rows before the first transaction row
            # Example: first_transaction_row=3 means skip rows 0 and 1 (rows 1 and 2 in file)
            skip_rows = max(0, first_row - 1)
        
        delimiter = schema.get("delimiter", ",")

        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            df = pd.read_excel(file_path, header=None, skiprows=skip_rows)
        else:
            from app.services.statement_analyzer import _expected_column_count, detect_csv_encoding
            encoding = detect_csv_encoding(file_path)
            csv_kwargs: dict = dict(header=None, skiprows=skip_rows, sep=delimiter, encoding=encoding)
            expected_cols = _expected_column_count(file_path, delimiter)
            if expected_cols and expected_cols > 1:
                csv_kwargs["names"] = list(range(expected_cols))
            df = pd.read_csv(file_path, **csv_kwargs)
        
        logger.info("Parsed statement file", {
            "file_path": file_path,
            "rows": len(df),
            "columns": list(df.columns),
            "skip_rows": skip_rows,
            "first_transaction_row": schema.get('first_transaction_row', 1)
        })
        
        # Get column mappings
        column_mappings = schema.get('column_mappings', {})
        date_col = column_mappings.get('date')
        description_col = column_mappings.get('description')  # Can be string or list
        amount_col = column_mappings.get('amount')
        balance_col = column_mappings.get('balance')  # Optional
        vendor_payee_col = column_mappings.get('vendor_payee')  # New
        category_col = column_mappings.get('category')  # New
        inflow_col = column_mappings.get('inflow')  # New
        outflow_col = column_mappings.get('outflow')  # New
        currency_col = column_mappings.get('currency')  # New
        has_inflow_mapping = _has_column_mapping(inflow_col)
        has_outflow_mapping = _has_column_mapping(outflow_col)
        invert_amount_sign = bool(schema.get('invert_amount_sign', False))
        raw_amount_column_inversions = schema.get('amount_column_inversions', {}) or {}

        # Normalize amount column mappings to a list (supports multi-column amount parsing)
        if isinstance(amount_col, str):
            amount_cols = [amount_col] if amount_col else []
        elif isinstance(amount_col, list):
            amount_cols = [str(col) for col in amount_col if str(col).strip()]
        else:
            amount_cols = []

        # Normalize per-column inversion map to string-keyed booleans for column refs
        amount_column_inversions = {}
        if isinstance(raw_amount_column_inversions, dict):
            amount_column_inversions = {
                str(column_ref): bool(is_inverted)
                for column_ref, is_inverted in raw_amount_column_inversions.items()
            }
        
        # Normalize description_col to list
        if isinstance(description_col, str):
            description_cols = [description_col]
        elif isinstance(description_col, list):
            description_cols = description_col
        else:
            description_cols = []
        
        # Validate required columns exist
        if (
            not _has_column_mapping(date_col)
            or not description_cols
            or (not amount_cols and not has_inflow_mapping and not has_outflow_mapping)
        ):
            raise ValueError(
                "Missing required column mappings: "
                f"date={date_col}, description={description_cols}, amount={amount_cols}, "
                f"inflow={inflow_col}, outflow={outflow_col}"
            )
        
        # Map column names (handle both column names and indices like "Column A")
        date_col_name = _resolve_column_name(df, date_col)
        description_col_names = [_resolve_column_name(df, col) for col in description_cols]
        amount_col_names = [_resolve_column_name(df, col) for col in amount_cols]
        balance_col_name = _resolve_column_name(df, balance_col) if balance_col else None
        vendor_payee_col_name = _resolve_column_name(df, vendor_payee_col) if vendor_payee_col else None
        category_col_name = _resolve_column_name(df, category_col) if category_col else None
        inflow_col_name = _resolve_column_name(df, inflow_col) if has_inflow_mapping else None
        outflow_col_name = _resolve_column_name(df, outflow_col) if has_outflow_mapping else None
        currency_col_name = _resolve_column_name(df, currency_col) if currency_col else None
        
        # Get first column index for transaction IDs (optional)
        first_column_index = schema.get('first_column_index')
        first_column_name = None
        if first_column_index is not None:
            # Convert index to string for resolution
            first_column_name = _resolve_column_name(df, str(first_column_index))
        
        # Validate all resolved
        failed_resolutions = []
        if date_col_name is None:
            failed_resolutions.append(f"date: {date_col}")
        if any(resolved is None for resolved in description_col_names):
            failed_descriptions = [
                description_cols[i]
                for i, resolved in enumerate(description_col_names)
                if resolved is None
            ]
            failed_resolutions.append(f"description: {failed_descriptions}")
        if amount_cols and any(resolved is None for resolved in amount_col_names):
            failed_amounts = [
                amount_cols[i]
                for i, resolved in enumerate(amount_col_names)
                if resolved is None
            ]
            failed_resolutions.append(f"amount: {failed_amounts}")
        if has_inflow_mapping and inflow_col_name is None:
            failed_resolutions.append(f"inflow: {inflow_col}")
        if has_outflow_mapping and outflow_col_name is None:
            failed_resolutions.append(f"outflow: {outflow_col}")
        
        if failed_resolutions:
            logger.error("Column resolution failed", {
                "failed_columns": failed_resolutions,
                "date_col": date_col,
                "date_col_name": date_col_name,
                "description_cols": description_cols,
                "description_col_names": description_col_names,
                "amount_cols": amount_cols,
                "amount_col_names": amount_col_names,
                "df_columns": list(df.columns),
                "df_column_types": [type(c).__name__ for c in df.columns],
                "has_headers": schema.get('has_headers', False),
                "first_transaction_row": schema.get('first_transaction_row', 1),
            })
            
            # Get bank name from schema if available
            bank_name = schema.get('bank_name', 'your bank')
            
            error_msg = (
                f"Could not resolve column names from mappings: {', '.join(failed_resolutions)}\n\n"
                f"This usually means the saved column mappings contain data values instead of column indices.\n\n"
                f"Action required:\n"
                f"1. The column mappings for '{bank_name}' are corrupted and need to be cleared\n"
                f"2. Re-upload your statement and manually re-map the columns\n"
                f"3. Column references should be numeric indices like '0', '1', '2' (preferred)\n"
                f"   - NOT column names like 'Date', 'Amount'\n"
                f"   - NOT column letters like 'Column A', 'Column B'\n"
                f"   - NOT data values like '02-01-2025', '21483,27'\n\n"
                f"Available columns in your file: {list(df.columns)}\n\n"
                f"If this issue persists, please contact support with bank name: {bank_name}"
            )
            raise ValueError(error_msg)
        
        # Parse transactions
        transactions = []
        date_format = schema.get('date_format', '%Y-%m-%d')
        currency = schema.get('currency', 'USD')
        number_format = schema.get('number_format', 'auto')
        amount_positive_is = schema.get('amount_positive_is', 'debit')
        if amount_col_names:
            try:
                has_explicit_sign = False
                for amount_col_name in amount_col_names:
                    amount_series = df[amount_col_name].astype(str)
                    if any(
                        ('-' in val) or (val.strip().startswith('(') and val.strip().endswith(')'))
                        for val in amount_series
                    ):
                        has_explicit_sign = True
                        break
                if has_explicit_sign:
                    amount_positive_is = 'signed'
            except Exception:
                pass
        
        for idx, row in df.iterrows():
            try:
                source_row_number = skip_rows + int(idx) + 1

                # Parse date
                date_str = str(row[date_col_name]).strip()
                date = _parse_date(date_str, date_format)
                
                # Get description - concatenate multiple columns if specified
                description_parts = []
                for desc_col_name in description_col_names:
                    if desc_col_name and pd.notna(row.get(desc_col_name)):
                        part = str(row[desc_col_name]).strip()
                        if part and part != 'nan' and part != 'None':
                            description_parts.append(part)
                description = ' '.join(description_parts).strip()
                
                # Get vendor/payee if available
                vendor_payee = None
                if vendor_payee_col_name and pd.notna(row.get(vendor_payee_col_name)):
                    vendor_payee = str(row[vendor_payee_col_name]).strip()
                    if vendor_payee == 'nan' or vendor_payee == 'None':
                        vendor_payee = None
                
                # Get category if available
                category = None
                if category_col_name and pd.notna(row.get(category_col_name)):
                    category = str(row[category_col_name]).strip()
                    if category == 'nan' or category == 'None':
                        category = None
                
                # Parse amount - check if inflow/outflow are mapped instead
                amount = None
                inflow = None
                outflow = None
                
                if inflow_col_name is not None or outflow_col_name is not None:
                    # Inflow and/or outflow are mapped - use them instead of amount
                    if inflow_col_name is not None and pd.notna(row.get(inflow_col_name)):
                        inflow_str = str(row[inflow_col_name]).strip()
                        if inflow_str and inflow_str != 'nan' and inflow_str != 'None' and inflow_str:
                            try:
                                inflow = _parse_amount(inflow_str, number_format)
                            except Exception:
                                inflow = None
                    if outflow_col_name is not None and pd.notna(row.get(outflow_col_name)):
                        outflow_str = str(row[outflow_col_name]).strip()
                        if outflow_str and outflow_str != 'nan' and outflow_str != 'None' and outflow_str:
                            try:
                                outflow = _parse_amount(outflow_str, number_format)
                            except Exception:
                                outflow = None
                    # Calculate amount from inflow/outflow
                    if inflow is not None and outflow is not None:
                        amount = inflow - outflow
                    elif inflow is not None:
                        amount = inflow
                    elif outflow is not None:
                        amount = -outflow
                    else:
                        amount = Decimal('0')

                    if invert_amount_sign:
                        amount = -amount
                else:
                    # Use one or more amount columns and sum all mapped amount components
                    amount_components: List[Decimal] = []
                    for i, amount_col_name in enumerate(amount_col_names):
                        raw_value = row.get(amount_col_name)
                        if not pd.notna(raw_value):
                            continue
                        amount_str = str(raw_value).strip()
                        if not amount_str or amount_str in {'nan', 'None'}:
                            continue

                        parsed_component = _parse_amount(amount_str, number_format)
                        source_column_ref = str(amount_cols[i])
                        if amount_column_inversions.get(source_column_ref, False):
                            parsed_component = -parsed_component
                        amount_components.append(parsed_component)

                    amount = sum(amount_components, Decimal('0'))

                    # Apply sign convention only when using a single amount column and no explicit inversion overrides.
                    apply_sign_convention = (
                        len(amount_col_names) == 1
                        and not invert_amount_sign
                        and not any(amount_column_inversions.values())
                    )
                    if apply_sign_convention:
                        if amount_positive_is == 'debit' and amount > 0:
                            amount = -abs(amount)  # Expenses are negative
                        elif amount_positive_is == 'credit' and amount < 0:
                            amount = abs(amount)  # Credits are positive

                    if invert_amount_sign:
                        amount = -amount
                    
                    # Set inflow/outflow based on amount
                    if amount > 0:
                        inflow = amount
                        outflow = None
                    elif amount < 0:
                        inflow = None
                        outflow = abs(amount)
                    else:
                        inflow = None
                        outflow = None
                
                # Get currency from column or use default
                transaction_currency = currency
                if currency_col_name and pd.notna(row.get(currency_col_name)):
                    currency_str = str(row[currency_col_name]).strip()
                    if currency_str and currency_str != 'nan' and currency_str != 'None':
                        transaction_currency = currency_str
                
                # Get balance if available
                balance = None
                if balance_col_name and pd.notna(row.get(balance_col_name)):
                    balance_str = str(row[balance_col_name]).strip()
                    balance = _parse_amount(balance_str, number_format)
                
                # Get transaction ID from first column if specified
                transaction_id = None
                if first_column_name and pd.notna(row.get(first_column_name)):
                    transaction_id_str = str(row[first_column_name]).strip()
                    if transaction_id_str and transaction_id_str != 'nan' and transaction_id_str != 'None':
                        transaction_id = transaction_id_str
                
                transaction = {
                    'date': date,
                    'vendor_payee': vendor_payee,
                    'description': description,
                    'category': category,
                    'amount': amount if amount is not None else Decimal('0'),
                    'inflow': inflow,
                    'outflow': outflow,
                    'balance': balance,
                    'currency': transaction_currency,
                    'source_row_number': source_row_number,
                }
                
                # Add transaction_id if available
                if transaction_id:
                    transaction['transaction_id'] = transaction_id
                
                transactions.append(transaction)
                
            except Exception as e:
                logger.warn("Failed to parse transaction row", {
                    "row": idx,
                    "error": str(e)
                })
                continue
        
        logger.info("Extracted transactions from statement", {
            "total": len(transactions),
            "file_path": file_path
        })
        
        return transactions
        
    except Exception as e:
        logger.error("Failed to parse statement file", {
            "file_path": file_path,
            "error": str(e)
        })
        raise


def _resolve_column_name(df: pd.DataFrame, column_ref: str):
    """
    Resolve column reference to actual column index.
    
    Since we always read files with header=None, DataFrame columns are integers (0, 1, 2, ...).
    This function validates that column_ref is a valid numeric index and returns the integer.
    
    Handles:
    - Column indices as numbers: "0", "1", "2" (preferred and only reliable method)
    
    Returns the actual column index (integer).
    """
    if not column_ref:
        return None
    
    # Validate that column_ref looks like a column reference, not data
    # If it contains date-like patterns, commas (for numbers), or looks like transaction data,
    # it's likely a data value, not a column reference
    if isinstance(column_ref, str):
        # Check if it looks like a date (contains dashes or slashes with numbers)
        if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$', column_ref):
            logger.error("Column reference looks like a date value, not a column index", {
                "column_ref": column_ref,
                "hint": "Column references should be numeric indices like '0', '1', '2'"
            })
            return None
        # Check if it looks like a large number or currency amount
        if re.match(r'^\d+[.,]\d+$', column_ref) or (column_ref.replace(',', '').replace('.', '').replace('-', '').isdigit() and len(column_ref) > 4):
            logger.error("Column reference looks like a numeric value, not a column index", {
                "column_ref": column_ref,
                "hint": "Column references should be numeric indices like '0', '1', '2'"
            })
            return None
    
    # Parse as numeric index (only reliable method with header=None)
    try:
        col_idx = int(column_ref)
        if 0 <= col_idx < len(df.columns):
            # Return the actual column index (integer)
            return col_idx
        else:
            logger.warn("Column index out of range", {
                "column_ref": column_ref,
                "max_columns": len(df.columns)
            })
            return None
    except (ValueError, TypeError):
        logger.warn("Could not parse column reference as integer", {
            "column_ref": column_ref,
            "column_ref_type": type(column_ref).__name__,
            "hint": "Column references must be numeric indices like '0', '1', '2'"
        })
        return None


def _parse_date(date_str: str, date_format: str) -> date:
    """Parse date string using provided format. Handles datetime strings with time components."""
    format_mappings = {
        'MM/DD/YYYY': '%m/%d/%Y',
        'DD/MM/YYYY': '%d/%m/%Y',
        'YYYY-MM-DD': '%Y-%m-%d',
        'MM-DD-YYYY': '%m-%d-%Y',
        'DD-MM-YYYY': '%d-%m-%Y',
        'YYYY/MM/DD': '%Y/%m/%d',
        'DD.MM.YYYY': '%d.%m.%Y',
        'DD Mon YYYY': '%d %b %Y',
        'DD/MM/YY': '%d/%m/%y',
        'DD-MM-YY': '%d-%m-%y',
        'YYYYMMDD': '%Y%m%d',
    }

    python_format = format_mappings.get(date_format, date_format)

    date_only = re.split(r'[T ]', date_str.strip())[0]

    for ds in ([date_str, date_only] if date_only != date_str.strip() else [date_str]):
        for fmt in [python_format, python_format + ' %H:%M:%S', python_format + 'T%H:%M:%S']:
            try:
                return datetime.strptime(ds.strip(), fmt).date()
            except ValueError:
                continue

    _FALLBACK_FORMATS = [
        '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d',
        '%d-%m-%Y', '%m-%d-%Y', '%d.%m.%Y', '%d %b %Y',
        '%d/%m/%y', '%d-%m-%y', '%Y%m%d',
    ]
    for ds in ([date_str, date_only] if date_only != date_str.strip() else [date_str]):
        for fmt in _FALLBACK_FORMATS:
            try:
                return datetime.strptime(ds.strip(), fmt).date()
            except ValueError:
                continue

    raise ValueError(f"Could not parse date: {date_str} with format: {date_format}")


def _parse_amount(amount_str: str, number_format: str = "auto") -> Decimal:
    """Parse amount string, handling currency symbols, commas, parentheses for negatives.

    Args:
        amount_str: Raw amount string from the CSV cell.
        number_format: Hint from the analyzer — ``"us"`` (comma=thousands, dot=decimal),
            ``"eu"`` (dot=thousands, comma=decimal), or ``"auto"`` (guess per value).

    Handles formats:
    - US:       1,234.56  -> 1234.56
    - European: 1.234,56  -> 1234.56
    - Swiss:    1'234.56  -> 1234.56
    - Plain:    -104.77   -> -104.77
    """
    amount_str = re.sub(r"[$€£¥zł₹₽₩₪₺₴₿]", '', amount_str, flags=re.IGNORECASE)
    # Strip ISO currency codes (e.g. "PLN", "USD", "EUR") — common in Polish/European bank exports
    amount_str = re.sub(r'\b[A-Z]{3}\b', '', amount_str)
    amount_str = amount_str.replace('\xa0', '').replace(' ', '').replace("'", '')

    if amount_str.startswith('(') and amount_str.endswith(')'):
        amount_str = '-' + amount_str[1:-1]

    if number_format == "eu":
        # Dots are thousands separators, commas are decimal
        amount_str = amount_str.replace('.', '').replace(',', '.')
    elif number_format == "us":
        # Commas are thousands separators, dots are decimal
        amount_str = amount_str.replace(',', '')
    else:
        # Auto-detect per value (original logic)
        if ',' in amount_str and '.' in amount_str:
            if amount_str.rfind(',') > amount_str.rfind('.'):
                amount_str = amount_str.replace('.', '').replace(',', '.')
            else:
                amount_str = amount_str.replace(',', '')
        elif ',' in amount_str and '.' not in amount_str:
            comma_count = amount_str.count(',')
            if comma_count > 1:
                amount_str = amount_str.replace(',', '')
            else:
                digits_after = amount_str.lstrip('-+').split(',')[-1]
                if len(digits_after) == 3 and digits_after.isdigit():
                    amount_str = amount_str.replace(',', '')
                else:
                    amount_str = amount_str.replace(',', '.')
        elif '.' in amount_str and ',' not in amount_str:
            if amount_str.count('.') > 1:
                amount_str = amount_str.replace('.', '')

    amount_str = amount_str.strip()

    try:
        return Decimal(amount_str)
    except Exception:
        raise ValueError(f"Could not parse amount: {amount_str}")


def _coerce_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def extract_merchant(description: str) -> str:
    """
    Extract merchant name from transaction description.
    
    Uses pattern matching to identify common merchant patterns:
    - "AMZN" → "Amazon"
    - "UBER" → "Uber"
    - "STARBUCKS" → "Starbucks"
    - etc.
    
    Args:
        description: Full transaction description
    
    Returns:
        Extracted merchant name, or original description if no pattern matches
    """
    description_upper = description.upper()
    
    # Common merchant patterns
    merchant_patterns = {
        r'\bAMZN\b': 'Amazon',
        r'\bUBER\b': 'Uber',
        r'\bUBER\s*EATS\b': 'Uber Eats',
        r'\bSTARBUCKS\b': 'Starbucks',
        r'\bWALMART\b': 'Walmart',
        r'\bTARGET\b': 'Target',
        r'\bCOSTCO\b': 'Costco',
        r'\bNETFLIX\b': 'Netflix',
        r'\bSPOTIFY\b': 'Spotify',
        r'\bAPPLE\b': 'Apple',
        r'\bGOOGLE\b': 'Google',
        r'\bMICROSOFT\b': 'Microsoft',
        r'\bPAYPAL\b': 'PayPal',
        r'\bVENMO\b': 'Venmo',
        r'\bSQUARE\b': 'Square',
    }
    
    # Try to match patterns
    for pattern, merchant_name in merchant_patterns.items():
        if re.search(pattern, description_upper):
            return merchant_name
    
    # If no pattern matches, try to extract first meaningful word/phrase
    # Remove common prefixes like "POS ", "ACH ", "DEBIT ", "CREDIT "
    cleaned = re.sub(r'^(POS|ACH|DEBIT|CREDIT|PURCHASE|PAYMENT)\s+', '', description_upper, flags=re.IGNORECASE)
    
    # Extract first 2-3 words as merchant name
    words = cleaned.split()[:3]
    if words:
        merchant = ' '.join(words)
        # Limit length
        if len(merchant) > 50:
            merchant = merchant[:50]
        return merchant
    
    # Fallback: return original description (truncated)
    return description[:100] if len(description) > 100 else description


def normalize_transaction(raw_tx: Dict, schema: Dict) -> Dict:
    """
    Normalize transaction format and validate data.
    
    Args:
        raw_tx: Raw transaction dict from parser
        schema: Parsing schema (for validation)
    
    Returns:
        Normalized transaction dict with validated fields
    """
    # Validate required fields
    if 'date' not in raw_tx or not raw_tx['date']:
        raise ValueError("Transaction missing date")
    if 'description' not in raw_tx or not raw_tx['description']:
        raise ValueError("Transaction missing description")
    if 'amount' not in raw_tx or raw_tx['amount'] is None:
        raise ValueError("Transaction missing amount")
    
    # Extract merchant (prefer vendor/payee if present)
    vendor_payee = raw_tx.get('vendor_payee')
    merchant = vendor_payee.strip() if isinstance(vendor_payee, str) and vendor_payee.strip() else extract_merchant(raw_tx['description'])
    
    amount = _coerce_decimal(raw_tx["amount"])
    balance = raw_tx.get("balance")
    if balance is not None and not isinstance(balance, Decimal):
        balance = _coerce_decimal(balance)

    # Build normalized transaction
    normalized = {
        'date': raw_tx['date'],
        'description': raw_tx['description'].strip(),
        'merchant': merchant,
        'vendor_payee': vendor_payee.strip() if isinstance(vendor_payee, str) and vendor_payee.strip() else None,
        'category': raw_tx.get('category'),
        'amount': amount,
        'currency': raw_tx.get('currency', schema.get('currency', 'USD')),
        'balance': balance,
    }

    source_row_number = raw_tx.get("source_row_number")
    if isinstance(source_row_number, int):
        normalized["source_row_number"] = source_row_number
    
    return normalized
