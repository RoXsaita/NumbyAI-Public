"""Comprehensive tests for statement analysis: delimiter detection, column detection,
number format, currency, date parsing, and full end-to-end analysis on diverse fixtures."""

import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from app.services.statement_analyzer import (
    _detect_amount_columns,
    _detect_balance_column,
    _detect_currency,
    _detect_date_column,
    _detect_description_and_vendor,
    _detect_first_transaction_row,
    _detect_number_format,
    _expected_column_count,
    _is_date_value,
    _is_numeric_value,
    analyze_statement_structure_from_file,
    detect_delimiter,
)
from app.tools.statement_parser import _parse_amount, _parse_date

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent.parent
SAMPLE_BANK = REPO_ROOT / "sample_bank_export.csv"


# ──────────────────────────────────────────────────────────
# detect_delimiter
# ──────────────────────────────────────────────────────────


class TestDetectDelimiter:
    def test_comma(self):
        assert detect_delimiter(str(FIXTURES_DIR / "uk_hsbc.csv")) == ","

    def test_semicolon(self):
        assert detect_delimiter(str(FIXTURES_DIR / "german_sparkasse.csv")) == ";"

    def test_tab(self):
        assert detect_delimiter(str(FIXTURES_DIR / "tab_delimited.csv")) == "\t"

    def test_pipe(self):
        assert detect_delimiter(str(FIXTURES_DIR / "pipe_delimited.csv")) == "|"

    def test_french_semicolon(self):
        assert detect_delimiter(str(FIXTURES_DIR / "french_bnp.csv")) == ";"

    def test_swiss_semicolon(self):
        assert detect_delimiter(str(FIXTURES_DIR / "swiss_ubs.csv")) == ";"

    def test_dutch_semicolon(self):
        assert detect_delimiter(str(FIXTURES_DIR / "dutch_ing.csv")) == ";"

    def test_us_chase_comma(self):
        assert detect_delimiter(str(FIXTURES_DIR / "us_chase.csv")) == ","

    def test_australian_comma(self):
        assert detect_delimiter(str(FIXTURES_DIR / "australian_nab.csv")) == ","

    def test_sample_bank_comma(self):
        if SAMPLE_BANK.exists():
            assert detect_delimiter(str(SAMPLE_BANK)) == ","

    def test_nonexistent_file_defaults_comma(self):
        assert detect_delimiter("/tmp/does_not_exist_xyz.csv") == ","

    def test_empty_file_defaults_comma(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("")
            f.flush()
            assert detect_delimiter(f.name) == ","
        os.unlink(f.name)


# ──────────────────────────────────────────────────────────
# _is_numeric_value
# ──────────────────────────────────────────────────────────


class TestIsNumericValue:
    @pytest.mark.parametrize(
        "val",
        [
            "123.45",
            "-123.45",
            "1,234.56",
            "-1,234.56",
            "1.234,56",
            "-1.234,56",
            "1234",
            "$1,234.56",
            "€1.234,56",
            "£123.45",
            "(500.00)",
            "1'234.56",
            "3 250,00",        # French: space thousands, comma decimal
            "3\xa0250,00",     # Non-breaking space thousands
            "0.00",
            "-0",
            "42",
        ],
    )
    def test_valid_numeric(self, val):
        assert _is_numeric_value(val), f"Expected True for {val!r}"

    @pytest.mark.parametrize(
        "val",
        [
            "",
            "hello",
            "REWE MARKT",
            "01/02/2026",
            "2026-01-02",
            "N/A",
            "nan",
            "Af",
            "Bij",
        ],
    )
    def test_non_numeric(self, val):
        assert not _is_numeric_value(val), f"Expected False for {val!r}"


# ──────────────────────────────────────────────────────────
# _is_date_value
# ──────────────────────────────────────────────────────────


class TestIsDateValue:
    @pytest.mark.parametrize(
        "val",
        [
            "2026-01-15",
            "15-01-2026",
            "15/01/2026",
            "01/15/2026",
            "2026/01/15",
            "15.01.2026",
            "2.1.2026",
            "15 Jan 2026",
            "2 Jan 2026",
            "15/01/26",
            "15-01-26",
            "20260115",
        ],
    )
    def test_valid_dates(self, val):
        assert _is_date_value(val), f"Expected True for {val!r}"

    @pytest.mark.parametrize("val", ["", "hello", "1234.56", "SALARY"])
    def test_non_dates(self, val):
        assert not _is_date_value(val), f"Expected False for {val!r}"


# ──────────────────────────────────────────────────────────
# _parse_amount
# ──────────────────────────────────────────────────────────


class TestParseAmount:
    def test_us_format_with_hint(self):
        assert _parse_amount("1,234.56", "us") == Decimal("1234.56")

    def test_us_negative(self):
        assert _parse_amount("-1,234.56", "us") == Decimal("-1234.56")

    def test_eu_format_with_hint(self):
        assert _parse_amount("1.234,56", "eu") == Decimal("1234.56")

    def test_eu_negative(self):
        assert _parse_amount("-1.234,56", "eu") == Decimal("-1234.56")

    def test_eu_comma_only(self):
        assert _parse_amount("850,00", "eu") == Decimal("850.00")

    def test_swiss_apostrophe(self):
        assert _parse_amount("1'234.56", "us") == Decimal("1234.56")

    def test_parentheses_negative(self):
        assert _parse_amount("(500.00)", "auto") == Decimal("-500.00")

    def test_currency_symbol_stripped(self):
        assert _parse_amount("$1,234.56", "us") == Decimal("1234.56")
        assert _parse_amount("€1.234,56", "eu") == Decimal("1234.56")
        assert _parse_amount("£123.45", "auto") == Decimal("123.45")

    def test_space_thousands_eu(self):
        assert _parse_amount("3 250,00", "eu") == Decimal("3250.00")

    def test_auto_detects_eu(self):
        assert _parse_amount("1.234,56", "auto") == Decimal("1234.56")

    def test_auto_detects_us(self):
        assert _parse_amount("1,234.56", "auto") == Decimal("1234.56")

    def test_plain_integer(self):
        assert _parse_amount("42", "auto") == Decimal("42")

    def test_plain_negative(self):
        assert _parse_amount("-94.30", "auto") == Decimal("-94.30")


# ──────────────────────────────────────────────────────────
# _parse_date
# ──────────────────────────────────────────────────────────


class TestParseDate:
    def test_us_format(self):
        d = _parse_date("01/15/2026", "MM/DD/YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_eu_slash_format(self):
        d = _parse_date("15/01/2026", "DD/MM/YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_iso_format(self):
        d = _parse_date("2026-01-15", "YYYY-MM-DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_eu_dot_format(self):
        d = _parse_date("15.01.2026", "DD.MM.YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_iso_slash_format(self):
        d = _parse_date("2026/01/15", "YYYY/MM/DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_dd_mon_yyyy(self):
        d = _parse_date("15 Jan 2026", "DD Mon YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_dd_mon_yyyy_single_digit(self):
        d = _parse_date("2 Jan 2026", "DD Mon YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_dd_mm_yy(self):
        d = _parse_date("15/01/26", "DD/MM/YY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_dd_mm_yy_dash(self):
        d = _parse_date("15-01-26", "DD-MM-YY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_yyyymmdd_compact(self):
        d = _parse_date("20260115", "YYYYMMDD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_datetime_with_time_stripped(self):
        d = _parse_date("2026-01-15 14:30:00", "YYYY-MM-DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_fallback_format(self):
        d = _parse_date("2026-01-15", "UNKNOWN_FORMAT")
        assert d.year == 2026 and d.month == 1 and d.day == 15


# ──────────────────────────────────────────────────────────
# Full analyze_statement_structure_from_file — fixture-based
# ──────────────────────────────────────────────────────────

DUMMY_USER_ID = "test-user-analyzer"


def _has_field(sm: dict, field_type: str) -> bool:
    """Check if a field type exists in suggested_mappings column_mappings (colIdx->fieldType)."""
    return field_type in sm["column_mappings"].values()


class TestAnalyzeGermanSparkasse:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "german_sparkasse.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD.MM.YYYY"

    def test_currency_eur(self):
        assert self.sm["currency"] == "EUR"

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 6


class TestAnalyzeFrenchBNP:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "french_bnp.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_currency_eur(self):
        assert self.sm["currency"] == "EUR"

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_inflow_outflow_or_amount_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount


class TestAnalyzeUKHSBC:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "uk_hsbc.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_currency_gbp(self):
        assert self.sm["currency"] == "GBP"

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount") or _has_field(self.sm, "inflow")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


class TestAnalyzeDutchING:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "dutch_ing.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_currency_eur(self):
        assert self.sm["currency"] == "EUR"


class TestAnalyzeTabDelimited:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "tab_delimited.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == "\t"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format_iso(self):
        assert "YYYY-MM-DD" in self.sm["date_format"]

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


class TestAnalyzePipeDelimited:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "pipe_delimited.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == "|"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")


class TestAnalyzeSwissUBS:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "swiss_ubs.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_currency_chf(self):
        assert self.sm["currency"] == "CHF"

    def test_date_format(self):
        assert self.sm["date_format"] == "DD.MM.YYYY"

    def test_inflow_outflow_or_amount(self):
        assert (_has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")) \
            or _has_field(self.sm, "amount")


class TestAnalyzeUSChase:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "us_chase.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_first_transaction_row_skips_header(self):
        assert self.sm["first_transaction_row"] >= 6

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount") or _has_field(self.sm, "inflow")

    def test_number_format_us(self):
        assert self.sm["number_format"] == "us"


class TestAnalyzeAustralianNAB:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "australian_nab.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


class TestAnalyzeUKBarclays:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "uk_barclays.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format_dd_mon_yyyy(self):
        assert self.sm["date_format"] == "DD Mon YYYY"

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")


class TestAnalyzeSampleBankExport:
    """Tests the complex sample_bank_export.csv with 9 header metadata rows."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        if not SAMPLE_BANK.exists():
            pytest.skip("sample_bank_export.csv not found")
        self.result = analyze_statement_structure_from_file(
            str(SAMPLE_BANK), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 10

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format_us(self):
        assert "MM/DD/YYYY" in self.sm["date_format"] or "DD/MM/YYYY" in self.sm["date_format"]

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_overall_confidence(self):
        assert self.result["confidence"] in ("high", "medium")


# ──────────────────────────────────────────────────────────
# Middle East bank fixtures
# ──────────────────────────────────────────────────────────


class TestAnalyzeUAEEnbd:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "uae_enbd.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_aed(self):
        assert self.sm["currency"] == "AED"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD/MM/YYYY"

    def test_number_format_us(self):
        assert self.sm["number_format"] == "us"

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 7


class TestAnalyzeSaudiAlRajhi:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "saudi_alrajhi.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_sar(self):
        assert self.sm["currency"] == "SAR"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD/MM/YYYY"

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


class TestAnalyzeEgyptCIB:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "egypt_cib.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_egp(self):
        assert self.sm["currency"] == "EGP"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 8


class TestAnalyzeIsraelLeumi:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "israel_leumi.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_ils(self):
        assert self.sm["currency"] == "ILS"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


class TestAnalyzeTurkeyIsbank:
    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "turkey_isbank.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_currency_try(self):
        assert self.sm["currency"] == "TRY"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD.MM.YYYY"

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Heavy metadata rows (11 rows before data)
# ──────────────────────────────────────────────────────────


class TestAnalyzeHeavyMetadata:
    """Tests a bank statement with 11 metadata rows + blank + header before data.

    This validates the system handles deeply-buried transaction data correctly.
    """

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "heavy_metadata_bank.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 14

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_detected(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_overall_confidence_not_low(self):
        assert self.result["confidence"] in ("high", "medium")


class TestExpectedColumnCount:
    """Tests that _expected_column_count picks the data-row width, not metadata."""

    def test_heavy_metadata_returns_data_width(self):
        result = _expected_column_count(str(FIXTURES_DIR / "heavy_metadata_bank.csv"), ",")
        assert result == 7  # Date,Description,Reference,Debit,Credit,Balance + 1 extra

    def test_german_sparkasse_returns_data_width(self):
        result = _expected_column_count(str(FIXTURES_DIR / "german_sparkasse.csv"), ";")
        assert result == 8

    def test_simple_csv_without_metadata(self):
        result = _expected_column_count(str(FIXTURES_DIR / "australian_nab.csv"), ",")
        assert result == 5


class TestIBANCurrencyInference:
    """Tests that currency detection falls back to IBAN country prefix."""

    def test_french_iban_infers_eur(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "french_bnp.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["currency"] == "EUR"

    def test_swiss_iban_infers_chf(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "swiss_ubs.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["currency"] == "CHF"

    def test_turkish_iban_infers_try(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "turkey_isbank.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["currency"] == "TRY"

    def test_saudi_iban_infers_sar(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "saudi_alrajhi.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["currency"] == "SAR"


# ══════════════════════════════════════════════════════════
# COMPREHENSIVE EDGE-CASE TESTS
# ══════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────
# _is_numeric_value — additional edge cases
# ──────────────────────────────────────────────────────────


class TestIsNumericValueEdgeCases:
    """Stress-test numeric detection with formats from around the world."""

    @pytest.mark.parametrize(
        "val",
        [
            "+1,234.56",           # explicit positive US
            "+1.234,56",           # explicit positive EU
            "1 234,56",            # French space-thousands, comma decimal
            "1\xa0234,56",         # non-breaking space thousands
            "₹1,234.56",          # Indian rupee symbol
            "₦1,234.56",          # Nigerian naira
            "R$ 1.234,56",         # Brazilian real with space
            "1,25,000.00",         # Indian lakh format (1 lakh 25 thousand)
            "AED 1,234.56",        # ISO code prefix
            "1,234.56 AED",        # ISO code suffix
            "45 000,00",           # Swedish/French space-thousands
            ".50",                 # leading dot decimal
            "-.50",                # negative leading dot
            "1234",                # plain integer
            "0",                   # zero
            "-0.00",               # negative zero
            "00.01",               # leading zeros
            "999999.99",           # no separators, large
            "1,234",               # could be US thousands or EU decimal
            "85.000,00",           # Turkish-style EU large number
            "142.500,75",          # EU with dot thousands
            "(1,200.00)",          # parenthetical negative US
            "(1.200,00)",          # parenthetical negative EU
            "$0.01",               # micro amount
            "€0,01",               # EU micro amount
            "1'234'567.89",        # Swiss multi-apostrophe
        ],
    )
    def test_valid_numeric_edge(self, val):
        assert _is_numeric_value(val), f"Expected True for {val!r}"

    @pytest.mark.parametrize(
        "val",
        [
            "N/A",
            "n/a",
            "-",
            "--",
            "...",
            "nan",
            "NaN",
            "None",
            "null",
            "PAID",
            "Cr",
            "Dr",
            "Pending",
            "01/02/2026",
            "2026-01-15",
            "15.01.2026",
            "REWE MARKT GMBH",
            "ATM Withdrawal",
            "Gutschrift",
            "Belastung",
            "Income",
            "Housing",
            "Bij",
            "Af",
            "REF-001",
            "TRF/002",
            "SAL-20260102",
            "NL91ABNA0417164300",    # IBAN
            "DE89370400440532013000", # German IBAN
        ],
    )
    def test_non_numeric_edge(self, val):
        assert not _is_numeric_value(val), f"Expected False for {val!r}"


# ──────────────────────────────────────────────────────────
# _parse_amount — comprehensive edge cases
# ──────────────────────────────────────────────────────────


class TestParseAmountEdgeCases:
    """Test amount parsing with every conceivable numeric format."""

    def test_explicit_positive_us(self):
        assert _parse_amount("+1,234.56", "us") == Decimal("1234.56")

    def test_explicit_positive_eu(self):
        assert _parse_amount("+1.234,56", "eu") == Decimal("1234.56")

    def test_french_space_thousands(self):
        assert _parse_amount("3 250,00", "eu") == Decimal("3250.00")

    def test_nbsp_thousands(self):
        assert _parse_amount("3\xa0250,00", "eu") == Decimal("3250.00")

    def test_swedish_space_thousands(self):
        assert _parse_amount("45 000,00", "eu") == Decimal("45000.00")

    def test_large_swedish(self):
        assert _parse_amount("128 450,75", "eu") == Decimal("128450.75")

    def test_indian_rupee_stripped(self):
        assert _parse_amount("₹1,234.56", "us") == Decimal("1234.56")

    def test_naira_stripped(self):
        assert _parse_amount("₦1,234.56", "us") == Decimal("1234.56")

    def test_brazilian_real(self):
        result = _parse_amount("R$ 1.234,56", "eu")
        assert result == Decimal("1234.56")

    def test_aed_prefix_stripped(self):
        assert _parse_amount("AED 1,234.56", "us") == Decimal("1234.56")

    def test_aed_suffix_stripped(self):
        assert _parse_amount("1,234.56 AED", "us") == Decimal("1234.56")

    def test_zero(self):
        assert _parse_amount("0", "auto") == Decimal("0")

    def test_zero_decimal(self):
        assert _parse_amount("0.00", "auto") == Decimal("0.00")

    def test_negative_zero(self):
        assert _parse_amount("-0.00", "auto") == Decimal("-0.00")

    def test_micro_amount(self):
        assert _parse_amount("0.01", "auto") == Decimal("0.01")

    def test_very_large_amount(self):
        assert _parse_amount("1,250,000.00", "us") == Decimal("1250000.00")

    def test_very_large_eu(self):
        assert _parse_amount("1.250.000,00", "eu") == Decimal("1250000.00")

    def test_millions_no_separator(self):
        assert _parse_amount("2500000.00", "us") == Decimal("2500000.00")

    def test_parenthetical_with_comma(self):
        assert _parse_amount("(1,200.00)", "us") == Decimal("-1200.00")

    def test_parenthetical_eu(self):
        assert _parse_amount("(1.200,00)", "eu") == Decimal("-1200.00")

    def test_leading_dot(self):
        assert _parse_amount(".50", "auto") == Decimal("0.50")

    def test_negative_leading_dot(self):
        assert _parse_amount("-.50", "auto") == Decimal("-0.50")

    def test_swiss_multi_apostrophe(self):
        assert _parse_amount("1'234'567.89", "us") == Decimal("1234567.89")

    def test_eu_comma_no_thousands(self):
        assert _parse_amount("850,00", "eu") == Decimal("850.00")

    def test_eu_comma_only_auto(self):
        result = _parse_amount("850,00", "auto")
        assert result == Decimal("850.00")

    def test_plain_integer(self):
        assert _parse_amount("450000", "auto") == Decimal("450000")

    def test_japanese_yen_no_decimal(self):
        assert _parse_amount("120000", "auto") == Decimal("120000")

    def test_polish_space_thousands(self):
        assert _parse_amount("8 500,00", "eu") == Decimal("8500.00")

    def test_korean_won_large(self):
        assert _parse_amount("4500000", "auto") == Decimal("4500000")

    def test_turkish_large_eu(self):
        assert _parse_amount("85.000,00", "eu") == Decimal("85000.00")

    def test_nigerian_large(self):
        assert _parse_amount("1,250,000.00", "us") == Decimal("1250000.00")

    def test_auto_detects_eu_from_rightmost(self):
        assert _parse_amount("1.234,56", "auto") == Decimal("1234.56")

    def test_auto_detects_us_from_rightmost(self):
        assert _parse_amount("1,234.56", "auto") == Decimal("1234.56")

    def test_auto_comma_only_two_digits(self):
        result = _parse_amount("234,56", "auto")
        assert result == Decimal("234.56")

    def test_auto_comma_only_three_digits(self):
        result = _parse_amount("1,234", "auto")
        assert result == Decimal("1234")

    def test_multiple_dots_eu(self):
        assert _parse_amount("1.234.567,89", "eu") == Decimal("1234567.89")

    def test_multiple_commas_us(self):
        assert _parse_amount("1,234,567.89", "us") == Decimal("1234567.89")

    def test_eur_symbol_eu(self):
        assert _parse_amount("€1.234,56", "eu") == Decimal("1234.56")

    def test_gbp_symbol_us(self):
        assert _parse_amount("£3,250.00", "us") == Decimal("3250.00")


# ──────────────────────────────────────────────────────────
# _parse_date — comprehensive edge cases
# ──────────────────────────────────────────────────────────


class TestParseDateEdgeCases:
    """Test date parsing with every format variant."""

    def test_datetime_iso_with_time(self):
        d = _parse_date("2026-01-15 14:30:00", "YYYY-MM-DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_datetime_iso_with_T(self):
        d = _parse_date("2026-01-15T14:30:00", "YYYY-MM-DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_single_digit_day_dot(self):
        d = _parse_date("2.1.2026", "DD.MM.YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_single_digit_month_dot(self):
        d = _parse_date("15.1.2026", "DD.MM.YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_short_month_name(self):
        d = _parse_date("15 Jan 2026", "DD Mon YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_feb_month_name(self):
        d = _parse_date("28 Feb 2026", "DD Mon YYYY")
        assert d.year == 2026 and d.month == 2 and d.day == 28

    def test_compact_yyyymmdd(self):
        d = _parse_date("20260115", "YYYYMMDD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_eu_dot_format(self):
        d = _parse_date("02.01.2026", "DD.MM.YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_us_slash(self):
        d = _parse_date("01/02/2026", "MM/DD/YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_eu_slash(self):
        d = _parse_date("02/01/2026", "DD/MM/YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_iso_slash(self):
        d = _parse_date("2026/01/15", "YYYY/MM/DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_two_digit_year(self):
        d = _parse_date("15/01/26", "DD/MM/YY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_two_digit_year_dash(self):
        d = _parse_date("15-01-26", "DD-MM-YY")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_dd_mm_yyyy_dash(self):
        d = _parse_date("02-01-2026", "DD-MM-YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 2

    def test_leading_whitespace(self):
        d = _parse_date("  2026-01-15  ", "YYYY-MM-DD")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_fallback_from_unknown_format(self):
        d = _parse_date("2026-01-15", "WEIRD_FORMAT_XYZ")
        assert d.year == 2026 and d.month == 1 and d.day == 15

    def test_year_end_date(self):
        d = _parse_date("31/12/2025", "DD/MM/YYYY")
        assert d.year == 2025 and d.month == 12 and d.day == 31

    def test_leap_year_feb29(self):
        d = _parse_date("29/02/2028", "DD/MM/YYYY")
        assert d.year == 2028 and d.month == 2 and d.day == 29

    def test_new_years_day(self):
        d = _parse_date("01/01/2026", "DD/MM/YYYY")
        assert d.year == 2026 and d.month == 1 and d.day == 1


# ──────────────────────────────────────────────────────────
# Full analysis — Arabic full statement
# ──────────────────────────────────────────────────────────


class TestAnalyzeArabicFull:
    """Arabic headers and descriptions (right-to-left script)."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "arabic_full.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_egp(self):
        assert self.sm["currency"] == "EGP"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD/MM/YYYY"

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 7

    def test_confidence_not_low(self):
        assert self.result["confidence"] in ("high", "medium")


# ──────────────────────────────────────────────────────────
# Full analysis — Indian SBI (lakh formatting)
# ──────────────────────────────────────────────────────────


class TestAnalyzeIndianSBI:
    """Indian bank with lakh numbering (1,25,000.00) and ₹ symbol."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "indian_sbi.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_inr(self):
        assert self.sm["currency"] == "INR"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


# ──────────────────────────────────────────────────────────
# Full analysis — Parentheses negatives
# ──────────────────────────────────────────────────────────


class TestAnalyzeParenthesesNegatives:
    """US bank using (500.00) for debits."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "parentheses_negatives.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_number_format_us(self):
        assert self.sm["number_format"] == "us"


# ──────────────────────────────────────────────────────────
# Full analysis — Brazilian Bradesco
# ──────────────────────────────────────────────────────────


class TestAnalyzeBrazilianBradesco:
    """Brazilian bank with R$ prefix and EU-style numbers (dot=thousands, comma=decimal)."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "brazilian_bradesco.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_currency_brl(self):
        assert self.sm["currency"] == "BRL"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Japanese MUFG
# ──────────────────────────────────────────────────────────


class TestAnalyzeJapaneseMUFG:
    """Japanese bank with kanji, yen (no decimals), and YYYY/MM/DD dates."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "japanese_mufg.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_jpy(self):
        assert self.sm["currency"] == "JPY"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert "YYYY" in self.sm["date_format"]

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Cr/Dr suffixed (HDFC India)
# ──────────────────────────────────────────────────────────


class TestAnalyzeCrDrSuffixed:
    """Indian HDFC bank with Dr/Cr column and lakh formatting."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "cr_dr_suffixed.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_inr(self):
        assert self.sm["currency"] == "INR"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 6


# ──────────────────────────────────────────────────────────
# Full analysis — Quoted fields with commas
# ──────────────────────────────────────────────────────────


class TestAnalyzeQuotedCommas:
    """CSV with quoted fields containing commas and double-quotes."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "quoted_commas.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_confidence_not_low(self):
        assert self.result["confidence"] in ("high", "medium")


# ──────────────────────────────────────────────────────────
# Full analysis — Sparse with blank rows
# ──────────────────────────────────────────────────────────


class TestAnalyzeSparseWithBlanks:
    """Statement with blank rows interspersed in the transaction data."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "sparse_with_blanks.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Credit card (reversed signs)
# ──────────────────────────────────────────────────────────


class TestAnalyzeCreditCardReversed:
    """Credit card where purchases are positive, payments are negative."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "credit_card_reversed.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 8


# ──────────────────────────────────────────────────────────
# Full analysis — Minimal three-column (no header)
# ──────────────────────────────────────────────────────────


class TestAnalyzeMinimalThreeCol:
    """Bare CSV with only date, description, amount — no header row."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "minimal_three_col.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row_is_1(self):
        assert self.sm["first_transaction_row"] == 1


# ──────────────────────────────────────────────────────────
# Full analysis — Extreme amounts (micro to millions)
# ──────────────────────────────────────────────────────────


class TestAnalyzeExtremeAmounts:
    """Very large and very small amounts including zero."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "extreme_amounts.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


# ──────────────────────────────────────────────────────────
# Full analysis — Polish mBank
# ──────────────────────────────────────────────────────────


class TestAnalyzePolishMBank:
    """Polish bank with zł/PLN, space-thousands, comma-decimal, semicolons."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "polish_mbank.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_currency_pln(self):
        assert self.sm["currency"] == "PLN"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert self.sm["date_format"] == "DD.MM.YYYY"

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Swedish Nordea
# ──────────────────────────────────────────────────────────


class TestAnalyzeSwedishNordea:
    """Swedish bank with SEK, space-thousands, comma-decimal, ISO dates."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "swedish_nordea.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_currency_sek(self):
        assert self.sm["currency"] == "SEK"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_date_format(self):
        assert "YYYY-MM-DD" in self.sm["date_format"]

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Nigerian GTBank
# ──────────────────────────────────────────────────────────


class TestAnalyzeNigerianGTBank:
    """Nigerian bank with NGN and ₦ symbol, large amounts."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "nigerian_gtbank.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_ngn(self):
        assert self.sm["currency"] == "NGN"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


# ──────────────────────────────────────────────────────────
# Full analysis — Chinese ICBC
# ──────────────────────────────────────────────────────────


class TestAnalyzeChineseICBC:
    """Chinese bank with hanzi characters and CNY, YYYY/MM/DD dates."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "chinese_icbc.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_cny(self):
        assert self.sm["currency"] == "CNY"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Korean Shinhan
# ──────────────────────────────────────────────────────────


class TestAnalyzeKoreanShinhan:
    """Korean bank with hangul, won (no decimals), YYYY/MM/DD dates."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "korean_shinhan.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_krw(self):
        assert self.sm["currency"] == "KRW"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Multi-currency statement
# ──────────────────────────────────────────────────────────


class TestAnalyzeMultiCurrency:
    """Statement with transactions in multiple currencies."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "multi_currency.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — No header, data starts immediately
# ──────────────────────────────────────────────────────────


class TestAnalyzeNoHeader:
    """CSV with no header row at all — data starts on line 1."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "no_header_direct.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] == 1


# ──────────────────────────────────────────────────────────
# Full analysis — Wide 16-column file
# ──────────────────────────────────────────────────────────


class TestAnalyzeWideFile:
    """File with 16 columns; only a few are relevant."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "wide_many_columns.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


# ──────────────────────────────────────────────────────────
# Full analysis — Unicode special chars (em-dashes, accents)
# ──────────────────────────────────────────────────────────


class TestAnalyzeUnicodeSpecialChars:
    """Descriptions with em-dashes, guillemets, accents, Nordic chars."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "unicode_special_chars.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_confidence_not_low(self):
        assert self.result["confidence"] in ("high", "medium")


# ──────────────────────────────────────────────────────────
# Full analysis — Deep metadata (20 preamble rows)
# ──────────────────────────────────────────────────────────


class TestAnalyzeDeepMetadata20Rows:
    """Statement with 20 metadata rows before the column header + data."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "deep_metadata_20rows.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_usd(self):
        assert self.sm["currency"] == "USD"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_first_transaction_row(self):
        assert self.sm["first_transaction_row"] >= 21

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")


# ──────────────────────────────────────────────────────────
# Full analysis — BOM UTF-8
# ──────────────────────────────────────────────────────────


class TestAnalyzeBomUtf8:
    """UTF-8 BOM-prefixed file (common Windows export)."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "bom_utf8.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_balance_detected(self):
        assert _has_field(self.sm, "balance")

    def test_confidence_not_low(self):
        assert self.result["confidence"] in ("high", "medium")


# ──────────────────────────────────────────────────────────
# Full analysis — Trailing commas
# ──────────────────────────────────────────────────────────


class TestAnalyzeTrailingCommas:
    """CSV with extra trailing commas on every line."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "trailing_commas.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Amounts with embedded currency text
# ──────────────────────────────────────────────────────────


class TestAnalyzeAmountsWithCurrencyText:
    """Amounts like 'AED 25,000.00' with ISO code embedded in the value."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "amounts_with_currency_text.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ","

    def test_currency_aed(self):
        assert self.sm["currency"] == "AED"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_inflow_outflow_or_amount(self):
        has_io = _has_field(self.sm, "inflow") and _has_field(self.sm, "outflow")
        has_amount = _has_field(self.sm, "amount")
        assert has_io or has_amount

    def test_description_detected(self):
        assert _has_field(self.sm, "description")


# ──────────────────────────────────────────────────────────
# Full analysis — Mixed sign conventions (+ and - prefixed, EU format)
# ──────────────────────────────────────────────────────────


class TestAnalyzeMixedSignConventions:
    """German-style amounts with explicit +/- prefix and comma decimal."""

    @pytest.fixture(autouse=True)
    def analyze(self):
        self.result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "mixed_sign_conventions.csv"), DUMMY_USER_ID
        )
        self.sm = self.result["suggested_mappings"]

    def test_delimiter(self):
        assert self.sm["delimiter"] == ";"

    def test_date_detected(self):
        assert _has_field(self.sm, "date")

    def test_amount_detected(self):
        assert _has_field(self.sm, "amount")

    def test_description_detected(self):
        assert _has_field(self.sm, "description")

    def test_number_format_eu(self):
        assert self.sm["number_format"] == "eu"


# ──────────────────────────────────────────────────────────
# _detect_number_format — edge cases
# ──────────────────────────────────────────────────────────


class TestDetectNumberFormat:
    """Test number format detection across various fixture files."""

    def test_german_is_eu(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "german_sparkasse.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["number_format"] == "eu"

    def test_french_is_eu(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "french_bnp.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["number_format"] == "eu"

    def test_swiss_is_auto_or_us(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "swiss_ubs.csv"), DUMMY_USER_ID
        )
        # Swiss apostrophe format (1'234.56) becomes 1234.56 after strip —
        # ambiguous without both separators, so "auto" or "us" is acceptable
        assert result["suggested_mappings"]["number_format"] in ("us", "auto")

    def test_us_chase_is_us(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "us_chase.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["number_format"] == "us"

    def test_turkish_is_eu(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "turkey_isbank.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["number_format"] == "eu"

    def test_brazilian_is_eu(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "brazilian_bradesco.csv"), DUMMY_USER_ID
        )
        assert result["suggested_mappings"]["number_format"] == "eu"


# ──────────────────────────────────────────────────────────
# Encoding detection
# ──────────────────────────────────────────────────────────


class TestEncodingDetection:
    """Ensure files with BOM and various encodings parse without error."""

    def test_bom_file_parses(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "bom_utf8.csv"), DUMMY_USER_ID
        )
        assert result["confidence"] != "low"

    def test_unicode_chars_parse(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "unicode_special_chars.csv"), DUMMY_USER_ID
        )
        assert result["confidence"] != "low"

    def test_arabic_encodes_correctly(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "arabic_full.csv"), DUMMY_USER_ID
        )
        assert _has_field(result["suggested_mappings"], "description")

    def test_japanese_encodes_correctly(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "japanese_mufg.csv"), DUMMY_USER_ID
        )
        assert _has_field(result["suggested_mappings"], "description")

    def test_chinese_encodes_correctly(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "chinese_icbc.csv"), DUMMY_USER_ID
        )
        assert _has_field(result["suggested_mappings"], "description")

    def test_korean_encodes_correctly(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "korean_shinhan.csv"), DUMMY_USER_ID
        )
        assert _has_field(result["suggested_mappings"], "description")

    def test_polish_encodes_correctly(self):
        result = analyze_statement_structure_from_file(
            str(FIXTURES_DIR / "polish_mbank.csv"), DUMMY_USER_ID
        )
        assert _has_field(result["suggested_mappings"], "description")


# ──────────────────────────────────────────────────────────
# Cross-cutting: every fixture should not crash
# ──────────────────────────────────────────────────────────


class TestNoCrashOnAllFixtures:
    """Smoke test: every fixture in the fixtures directory must parse without exceptions."""

    @pytest.fixture(autouse=True)
    def collect_fixtures(self):
        self.fixtures = sorted(FIXTURES_DIR.glob("*.csv"))

    def test_all_fixtures_parse_without_error(self):
        failures = []
        for fixture in self.fixtures:
            try:
                result = analyze_statement_structure_from_file(
                    str(fixture), DUMMY_USER_ID
                )
                assert "suggested_mappings" in result
                assert "confidence" in result
            except Exception as e:
                failures.append(f"{fixture.name}: {e}")
        assert not failures, f"Fixtures that crashed:\n" + "\n".join(failures)

    def test_all_fixtures_detect_date(self):
        failures = []
        for fixture in self.fixtures:
            try:
                result = analyze_statement_structure_from_file(
                    str(fixture), DUMMY_USER_ID
                )
                if not _has_field(result["suggested_mappings"], "date"):
                    failures.append(fixture.name)
            except Exception:
                pass  # crash tested separately
        assert not failures, f"Fixtures missing date detection: {failures}"

    def test_all_fixtures_detect_description(self):
        failures = []
        for fixture in self.fixtures:
            try:
                result = analyze_statement_structure_from_file(
                    str(fixture), DUMMY_USER_ID
                )
                if not _has_field(result["suggested_mappings"], "description"):
                    failures.append(fixture.name)
            except Exception:
                pass
        assert not failures, f"Fixtures missing description detection: {failures}"

    def test_all_fixtures_detect_amount_or_inflow_outflow(self):
        failures = []
        for fixture in self.fixtures:
            try:
                result = analyze_statement_structure_from_file(
                    str(fixture), DUMMY_USER_ID
                )
                sm = result["suggested_mappings"]
                has_amount = _has_field(sm, "amount")
                has_io = _has_field(sm, "inflow") and _has_field(sm, "outflow")
                if not has_amount and not has_io:
                    failures.append(fixture.name)
            except Exception:
                pass
        assert not failures, f"Fixtures missing amount detection: {failures}"
