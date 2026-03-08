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
