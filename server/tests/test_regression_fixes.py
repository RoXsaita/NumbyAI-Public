#!/usr/bin/env python3
"""Regression tests for recent review findings."""

import asyncio
import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, ".")

from starlette.requests import Request

from app.database import SessionLocal, CategorizationPreference, RuleAnalysisFinding, Transaction, get_or_create_test_user
from app.main import (
    _apply_rule_analysis_finding,
    _preview_sessions,
    apply_rule_analysis_finding,
    commit_preview,
    get_review_conflicts,
    get_review_queue,
    process_statement_pipeline,
    update_transaction,
)
from app.services import llm_service
from app.services.review_service import _build_review_prompt
from app.services.rule_analysis_service import analyze_rules_for_user
from app.tools.category_helpers import MANUAL_REVIEW
from app.tools.save_preferences import save_preferences_handler
from app.tools.statement_parser import parse_csv_statement
from tests import test_e2e_categorization as e2e_categorization


class _MockResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _json_request(method: str, path: str, payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )


def _empty_request(method: str, path: str) -> Request:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [],
        },
        receive,
    )


class OllamaAvailabilityTests(unittest.TestCase):
    @patch("app.services.llm_service.requests.get")
    def test_model_name_match_is_exact(self, mock_get):
        mock_get.return_value = _MockResponse(
            {"models": [{"name": "qwen3:14b-instruct"}]}
        )
        with patch.object(llm_service.settings, "ollama_model", "qwen3:14b"):
            status = llm_service.get_ollama_status()

        self.assertTrue(status["reachable"])
        self.assertFalse(status["model_available"])
        self.assertFalse(status["available"])

    @patch("app.services.llm_service.requests.get")
    def test_untagged_model_matches_latest_alias(self, mock_get):
        mock_get.return_value = _MockResponse(
            {"models": [{"name": "qwen3:latest"}]}
        )
        with patch.object(llm_service.settings, "ollama_model", "qwen3"):
            status = llm_service.get_ollama_status()

        self.assertTrue(status["model_available"])
        self.assertTrue(status["available"])


class ParsingPreferenceRegressionTests(unittest.TestCase):
    def test_save_preferences_parsing_schema_keeps_inversion_flags(self):
        user_id = get_or_create_test_user()
        bank_name = "ParsingBank-test-fixture"

        db = SessionLocal()
        try:
            db.query(CategorizationPreference).filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.bank_name == bank_name,
                CategorizationPreference.preference_type == "parsing",
            ).delete()
            db.commit()
        finally:
            db.close()

        result = asyncio.run(
            save_preferences_handler(
                preferences=[
                    {
                        "name": f"parsing_{bank_name}_csv",
                        "bank_name": bank_name,
                        "rule": {
                            "column_mappings": {
                                "date": "0",
                                "description": ["1"],
                                "amount": ["2", "3"],
                            },
                            "amount_column_inversions": {"3": True},
                            "invert_amount_sign": True,
                            "first_transaction_row": 4,
                            "date_format": "DD/MM/YYYY",
                        },
                    }
                ],
                preference_type="parsing",
                user_id=user_id,
            )
        )

        self.assertEqual(result["structuredContent"]["summary"]["errors"], 0)

        db = SessionLocal()
        try:
            saved = db.query(CategorizationPreference).filter(
                CategorizationPreference.user_id == user_id,
                CategorizationPreference.bank_name == bank_name,
                CategorizationPreference.preference_type == "parsing",
            ).one()

            self.assertTrue(saved.rule["invert_amount_sign"])
            self.assertEqual(saved.rule["amount_column_inversions"], {"3": True})
            self.assertEqual(saved.rule["column_mappings"]["amount"], ["2", "3"])
            self.assertEqual(saved.rule["first_transaction_row"], 4)
        finally:
            db.close()

    def test_rule_analysis_conflict_apply_honors_chosen_category_override(self):
        user_id = get_or_create_test_user()
        tx_id = str(uuid4())

        db = SessionLocal()
        try:
            db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.user_id == user_id,
            ).delete()
            db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.id == tx_id,
            ).delete()
            db.commit()

            tx = Transaction(
                id=tx_id,
                user_id=user_id,
                date=date(2026, 2, 15),
                description="Conflict override regression",
                merchant="Test Merchant",
                amount=Decimal("-12.34"),
                currency="PLN",
                category="Other",
                bank_name="Regression Bank",
                review_status="conflict",
                review_category="Food & Groceries",
            )
            db.add(tx)
            db.flush()

            finding = RuleAnalysisFinding(
                run_id=str(uuid4()),
                user_id=user_id,
                finding_type="tx_conflict",
                status="open",
                confidence=Decimal("0.91"),
                bank_name="Regression Bank",
                payload_json={
                    "transaction_id": tx_id,
                    "current_category": "Other",
                    "suggested_category": "Food & Groceries",
                },
            )
            db.add(finding)
            db.flush()

            result = _apply_rule_analysis_finding(
                db=db,
                user_id=user_id,
                finding=finding,
                chosen_category="Travel",
            )

            self.assertEqual(result["category"], "Travel")
            self.assertEqual(tx.category, "Travel")
            self.assertEqual(tx.review_status, "resolved")
        finally:
            db.rollback()
            db.close()


class LlmProviderSelectionRegressionTests(unittest.TestCase):
    @patch("app.services.llm_service.requests.get")
    def test_unset_provider_uses_legacy_ollama_default(self, mock_get):
        mock_get.return_value = _MockResponse(
            {"models": [{"name": "qwen3.5:9b"}]}
        )
        with patch.object(llm_service.settings, "llm_provider", None), patch.object(
            llm_service.settings, "ollama_model", "qwen3.5:9b"
        ):
            status = llm_service.get_llm_status()

        self.assertEqual(status["provider"], "ollama")
        self.assertTrue(status["available"])

class E2ECategorizationReportTests(unittest.TestCase):
    def test_report_fails_when_category_breakdown_unavailable(self):
        events = [
            {
                "type": "complete",
                "result": {
                    "transactions_processed": 10,
                    "dashboard": {"category_summaries": []},
                },
            }
        ]

        with patch.object(
            e2e_categorization, "fetch_transaction_breakdown", return_value=({}, 0)
        ):
            passed = e2e_categorization.report(events)

        self.assertFalse(passed)

    def test_report_still_passes_for_good_other_ratio(self):
        events = [
            {
                "type": "complete",
                "result": {
                    "transactions_processed": 10,
                    "dashboard": {
                        "category_summaries": [
                            {"category": "Food & Groceries", "transaction_count": 9},
                            {"category": "Other", "transaction_count": 1},
                        ]
                    },
                },
            }
        ]

        passed = e2e_categorization.report(events)

        self.assertTrue(passed)


class StatementParserRegressionTests(unittest.TestCase):
    def _write_csv(self, line: str) -> str:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        csv_path = Path(temp_dir.name) / "statement.csv"
        csv_path.write_text(f"{line}\n", encoding="utf-8")
        return str(csv_path)

    def test_inflow_column_zero_is_treated_as_valid_mapping(self):
        file_path = self._write_csv("100.00,2026-01-01,Salary")
        schema = {
            "column_mappings": {
                "inflow": "0",
                "date": "1",
                "description": "2",
            },
            "date_format": "YYYY-MM-DD",
        }

        transactions = parse_csv_statement(file_path, schema)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["amount"], Decimal("100.00"))
        self.assertEqual(transactions[0]["inflow"], Decimal("100.00"))
        self.assertIsNone(transactions[0]["outflow"])

    def test_invalid_inflow_mapping_raises_value_error(self):
        file_path = self._write_csv("100.00,2026-01-01,Salary")
        schema = {
            "column_mappings": {
                "inflow": "9",
                "date": "1",
                "description": "2",
            },
            "date_format": "YYYY-MM-DD",
        }

        with self.assertRaises(ValueError) as ctx:
            parse_csv_statement(file_path, schema)

        self.assertIn("inflow: 9", str(ctx.exception))


class ReviewQueueOrderingRegressionTests(unittest.TestCase):
    def test_conflicts_are_prioritized_before_manual_review(self):
        user_id = get_or_create_test_user()
        bank_name = f"RegressionBank-{uuid4().hex[:8]}"
        since_dt = datetime.now(timezone.utc) - timedelta(days=1)

        db = SessionLocal()
        conflict_id: str | None = None
        try:
            conflict_tx = Transaction(
                user_id=user_id,
                date=date.today(),
                description="Regression conflict row",
                merchant="Conflict Merchant",
                amount=Decimal("-10.00"),
                currency="USD",
                category="Shopping",
                bank_name=bank_name,
                review_status="conflict",
                created_at=datetime.now(timezone.utc),
            )
            manual_tx = Transaction(
                user_id=user_id,
                date=date.today(),
                description="Regression manual row",
                merchant="Manual Merchant",
                amount=Decimal("-999.00"),
                currency="USD",
                category=MANUAL_REVIEW,
                bank_name=bank_name,
                created_at=datetime.now(timezone.utc),
            )
            db.add_all([conflict_tx, manual_tx])
            db.commit()
            db.refresh(conflict_tx)
            conflict_id = str(conflict_tx.id)
        finally:
            db.close()

        try:
            query_string = urlencode({
                "bank_name": bank_name,
                "since": since_dt.isoformat(),
            }).encode("utf-8")
            request = Request({
                "type": "http",
                "method": "GET",
                "path": "/api/transactions/review-queue",
                "query_string": query_string,
                "headers": [],
            })
            response = asyncio.run(get_review_queue(request))
            response_body = response.body.decode("utf-8")
            self.assertEqual(response.status_code, 200, response_body)
            payload = json.loads(response.body)
            self.assertGreaterEqual(payload["total_count"], 2)
            self.assertEqual(payload["transactions"][0]["review_priority"], "ai_conflict")
            self.assertEqual(payload["transactions"][0]["id"], conflict_id)
            self.assertEqual(payload["transactions"][1]["review_priority"], "manual_review")
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()

    def test_rule_analysis_apply_accepts_empty_post_body(self):
        user_id = get_or_create_test_user()
        tx_id = str(uuid4())
        finding_id = str(uuid4())

        db = SessionLocal()
        try:
            db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.user_id == user_id,
                RuleAnalysisFinding.id == finding_id,
            ).delete()
            db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.id == tx_id,
            ).delete()
            db.commit()

            tx = Transaction(
                id=tx_id,
                user_id=user_id,
                date=date(2026, 2, 16),
                description="Empty body apply regression",
                merchant="Test Merchant",
                amount=Decimal("-22.00"),
                currency="PLN",
                category="Other",
                bank_name="Regression Bank",
                review_status="conflict",
                review_category="Travel",
            )
            db.add(tx)
            db.flush()

            finding = RuleAnalysisFinding(
                id=finding_id,
                run_id=str(uuid4()),
                user_id=user_id,
                finding_type="tx_conflict",
                status="open",
                confidence=0.9,
                bank_name="Regression Bank",
                payload_json={
                    "transaction_id": tx_id,
                    "current_category": "Other",
                    "suggested_category": "Travel",
                },
            )
            db.add(finding)
            db.commit()
        finally:
            db.close()

        request = _empty_request(
            "POST",
            f"/api/rules/analyze/findings/{finding_id}/apply",
        )
        response = asyncio.run(apply_rule_analysis_finding(request, finding_id))
        self.assertEqual(response.status_code, 200, response.body.decode("utf-8"))

        db = SessionLocal()
        try:
            updated_tx = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.id == tx_id,
            ).one()
            updated_finding = db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.user_id == user_id,
                RuleAnalysisFinding.id == finding_id,
            ).one()

            self.assertEqual(updated_tx.category, "Travel")
            self.assertEqual(updated_finding.status, "applied")
        finally:
            db.query(RuleAnalysisFinding).filter(
                RuleAnalysisFinding.user_id == user_id,
                RuleAnalysisFinding.id == finding_id,
            ).delete()
            db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.id == tx_id,
            ).delete()
            db.commit()
            db.close()


class ReviewPromptRegressionTests(unittest.TestCase):
    def test_review_prompt_requires_english_reasons(self):
        prompt = _build_review_prompt(
            transactions=[
                {
                    "id": 1,
                    "date": "2026-03-05",
                    "description": "SKLEP SPOZYWCZY",
                    "merchant": "Biedronka",
                    "amount": -12.34,
                    "category": "Shopping",
                }
            ],
            rules=[],
        )

        self.assertIn('"reason": one short sentence in English', prompt)


class ReviewScopeRegressionTests(unittest.TestCase):
    @patch("app.main.review_transactions_batch")
    @patch("app.main.categorize_transactions_batch")
    @patch("app.main.apply_categorization_rules")
    @patch("app.main.normalize_transaction")
    @patch("app.main.parse_csv_statement")
    @patch("app.main.check_existing_parsing_preferences")
    def test_reviewer_only_checks_ai_categorizations(
        self,
        mock_check_schema,
        mock_parse_csv,
        mock_normalize_transaction,
        mock_apply_rules,
        mock_categorize_batch,
        mock_review_batch,
    ):
        user_id = get_or_create_test_user()
        mock_check_schema.return_value = {
            "column_mappings": {"date": "0", "description": "1", "amount": "2"},
            "date_format": "YYYY-MM-DD",
            "currency": "USD",
            "first_transaction_row": 1,
        }
        parsed_rows = [
            {
                "date": date(2026, 3, 5),
                "description": "CARREFOUR CITY",
                "merchant": "Carrefour",
                "amount": Decimal("-12.34"),
                "currency": "USD",
            },
            {
                "date": date(2026, 3, 5),
                "description": "WHOLE FOODS MARKET",
                "merchant": "Whole Foods",
                "amount": Decimal("-54.32"),
                "currency": "USD",
            },
        ]
        mock_parse_csv.return_value = parsed_rows
        mock_normalize_transaction.side_effect = lambda tx, _schema: tx
        mock_apply_rules.return_value = (
            {1: "Food & Groceries"},
            [{**parsed_rows[1], "id": 2}],
        )
        mock_categorize_batch.return_value = [{"id": 2, "category": "Shopping"}]
        mock_review_batch.return_value = [{"id": 2, "status": "confirmed"}]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "statement.csv"
            file_path.write_text("unused\n", encoding="utf-8")
            result = asyncio.run(
                process_statement_pipeline(
                    file_path=file_path,
                    bank_name="RegressionBank",
                    net_flow=None,
                    header_mapping=None,
                    user_id=user_id,
                    dry_run=True,
                )
            )

        review_arg = mock_review_batch.call_args.args[0]
        self.assertEqual([tx["id"] for tx in review_arg], [2])
        self.assertEqual(result["transactions"][0]["category_source"], "rule")
        self.assertEqual(result["transactions"][1]["category_source"], "ai")

    @patch("app.main.review_transactions_batch")
    @patch("app.main.categorize_transactions_batch")
    @patch("app.main.get_llm_status")
    @patch("app.main.apply_categorization_rules")
    @patch("app.main.normalize_transaction")
    @patch("app.main.parse_csv_statement")
    @patch("app.main.check_existing_parsing_preferences")
    def test_pipeline_forwards_requested_provider_to_categorizer_and_reviewer(
        self,
        mock_check_schema,
        mock_parse_csv,
        mock_normalize_transaction,
        mock_apply_rules,
        mock_get_llm_status,
        mock_categorize_batch,
        mock_review_batch,
    ):
        user_id = get_or_create_test_user()
        mock_check_schema.return_value = {
            "column_mappings": {"date": "0", "description": "1", "amount": "2"},
            "date_format": "YYYY-MM-DD",
            "currency": "USD",
            "first_transaction_row": 1,
        }
        parsed_rows = [
            {
                "date": date(2026, 3, 5),
                "description": "OPENAI SUBSCRIPTION",
                "merchant": "OpenAI",
                "amount": Decimal("-20.00"),
                "currency": "USD",
            }
        ]
        mock_parse_csv.return_value = parsed_rows
        mock_normalize_transaction.side_effect = lambda tx, _schema: tx
        mock_apply_rules.return_value = ({}, [{**parsed_rows[0], "id": 1}])
        mock_get_llm_status.return_value = {"provider": "ollama", "available": True}
        mock_categorize_batch.return_value = [{"id": 1, "category": "Shopping"}]
        mock_review_batch.return_value = [{"id": 1, "status": "confirmed"}]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "statement.csv"
            file_path.write_text("unused\n", encoding="utf-8")
            asyncio.run(
                process_statement_pipeline(
                    file_path=file_path,
                    bank_name="ProviderBank",
                    net_flow=None,
                    header_mapping=None,
                    user_id=user_id,
                    dry_run=True,
                    llm_provider="ollama",
                )
            )

        self.assertEqual(mock_get_llm_status.call_args.kwargs["provider_override"], "ollama")
        self.assertEqual(mock_categorize_batch.call_args.kwargs["llm_provider"], "ollama")
        self.assertEqual(mock_review_batch.call_args.kwargs["llm_provider"], "ollama")


class LowValueManualReviewRegressionTests(unittest.TestCase):
    @patch("app.main.review_transactions_batch")
    @patch("app.main.categorize_transactions_batch")
    @patch("app.main.apply_categorization_rules")
    @patch("app.main.normalize_transaction")
    @patch("app.main.parse_csv_statement")
    @patch("app.main.check_existing_parsing_preferences")
    def test_small_pln_manual_reviews_auto_fall_back_to_other(
        self,
        mock_check_schema,
        mock_parse_csv,
        mock_normalize_transaction,
        mock_apply_rules,
        mock_categorize_batch,
        mock_review_batch,
    ):
        user_id = get_or_create_test_user()
        mock_check_schema.return_value = {
            "column_mappings": {"date": "0", "description": "1", "amount": "2"},
            "date_format": "YYYY-MM-DD",
            "currency": "PLN",
            "first_transaction_row": 1,
        }
        parsed_rows = [
            {
                "date": date(2026, 3, 5),
                "description": "NIEZNANA PLATNOSC",
                "merchant": "NIEZNANA PLATNOSC",
                "amount": Decimal("-19.99"),
                "currency": "PLN",
            }
        ]
        mock_parse_csv.return_value = parsed_rows
        mock_normalize_transaction.side_effect = lambda tx, _schema: tx
        mock_apply_rules.return_value = ({}, [{**parsed_rows[0], "id": 1}])
        mock_categorize_batch.return_value = [{"id": 1, "category": MANUAL_REVIEW}]
        mock_review_batch.return_value = [{"id": 1, "status": "confirmed"}]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "statement.csv"
            file_path.write_text("unused\n", encoding="utf-8")
            result = asyncio.run(
                process_statement_pipeline(
                    file_path=file_path,
                    bank_name="FallbackBank",
                    net_flow=None,
                    header_mapping=None,
                    user_id=user_id,
                    dry_run=True,
                )
            )

        self.assertEqual(result["manual_review_count"], 0)
        self.assertEqual(result["transactions"][0]["category"], "Other")
        self.assertEqual(result["transactions"][0]["category_source"], "ai")
        self.assertEqual(result["category_distribution"]["Other"], 1)
        review_arg = mock_review_batch.call_args.args[0]
        self.assertEqual(review_arg[0]["category"], "Other")


class PreviewCommitMetadataRegressionTests(unittest.TestCase):
    @patch("app.main.review_transactions_batch")
    @patch("app.main.categorize_transactions_batch")
    @patch("app.main.apply_categorization_rules")
    @patch("app.main.normalize_transaction")
    @patch("app.main.parse_csv_statement")
    @patch("app.main.check_existing_parsing_preferences")
    def test_commit_persists_preview_category_source_and_review_metadata(
        self,
        mock_check_schema,
        mock_parse_csv,
        mock_normalize_transaction,
        mock_apply_rules,
        mock_categorize_batch,
        mock_review_batch,
    ):
        user_id = get_or_create_test_user()
        bank_name = f"PreviewCommitBank-{uuid4().hex[:8]}"
        mock_check_schema.return_value = {
            "column_mappings": {"date": "0", "description": "1", "amount": "2"},
            "date_format": "YYYY-MM-DD",
            "currency": "USD",
            "first_transaction_row": 1,
        }
        parsed_rows = [
            {
                "date": date(2026, 3, 5),
                "description": "WHOLE FOODS MARKET",
                "merchant": "Whole Foods",
                "amount": Decimal("-54.32"),
                "currency": "USD",
            }
        ]
        mock_parse_csv.return_value = parsed_rows
        mock_normalize_transaction.side_effect = lambda tx, _schema: tx
        mock_apply_rules.return_value = ({}, [{**parsed_rows[0], "id": 1}])
        mock_categorize_batch.return_value = [{"id": 1, "category": "Shopping"}]
        mock_review_batch.return_value = [{
            "id": 1,
            "status": "conflict",
            "suggested_category": "Food & Groceries",
            "reason": "Merchant is usually groceries.",
        }]

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "statement.csv"
            file_path.write_text("unused\n", encoding="utf-8")
            preview = asyncio.run(
                process_statement_pipeline(
                    file_path=file_path,
                    bank_name=bank_name,
                    net_flow=None,
                    header_mapping=None,
                    user_id=user_id,
                    dry_run=True,
                )
            )

        self.assertEqual(preview["transactions"][0]["category_source"], "ai")
        self.assertEqual(preview["transactions"][0]["review_status"], "conflict")
        self.assertEqual(preview["transactions"][0]["review_category"], "Food & Groceries")

        preview_id = preview["preview_id"]
        request = _json_request("POST", "/api/statements/commit", {"preview_id": preview_id})

        try:
            response = asyncio.run(commit_preview(request))
            self.assertEqual(response.status_code, 200, response.body.decode("utf-8"))
            self.assertNotIn(preview_id, _preview_sessions)

            verify_db = SessionLocal()
            try:
                refreshed = verify_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).one()
                self.assertEqual(refreshed.category, "Shopping")
                self.assertEqual(refreshed.category_source, "ai")
                self.assertEqual(refreshed.review_status, "conflict")
                self.assertEqual(refreshed.review_category, "Food & Groceries")
                self.assertEqual(refreshed.review_reason, "Merchant is usually groceries.")
            finally:
                verify_db.close()
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


class TransactionPatchMetadataRegressionTests(unittest.TestCase):
    def test_generic_transaction_patch_marks_manual_source_and_clears_stale_review_metadata(self):
        user_id = get_or_create_test_user()
        bank_name = f"PatchMetadataBank-{uuid4().hex[:8]}"

        db = SessionLocal()
        tx_id: str | None = None
        try:
            tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 5),
                description="Original category assignment",
                merchant="Original Merchant",
                amount=Decimal("-25.00"),
                currency="USD",
                category="Shopping",
                category_source="rule",
                bank_name=bank_name,
                review_status="confirmed",
                review_category="Food & Groceries",
                review_reason="Stale reviewer note",
                created_at=datetime.now(timezone.utc),
            )
            db.add(tx)
            db.commit()
            db.refresh(tx)
            tx_id = str(tx.id)
        finally:
            db.close()

        request = _json_request(
            "PATCH",
            "/api/transactions",
            {"id": tx_id, "updates": {"category": "Entertainment"}},
        )

        try:
            response = asyncio.run(update_transaction(request))
            response_body = response.body.decode("utf-8")
            self.assertEqual(response.status_code, 200, response_body)
            payload = json.loads(response.body)
            self.assertEqual(payload["category"], "Entertainment")
            self.assertEqual(payload["category_source"], "manual")
            self.assertIsNone(payload["review_status"])

            verify_db = SessionLocal()
            try:
                refreshed = verify_db.query(Transaction).filter(Transaction.id == tx_id).first()
                self.assertIsNotNone(refreshed)
                self.assertEqual(refreshed.category, "Entertainment")
                self.assertEqual(refreshed.category_source, "manual")
                self.assertIsNone(refreshed.review_status)
                self.assertIsNone(refreshed.review_category)
                self.assertIsNone(refreshed.review_reason)
            finally:
                verify_db.close()
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(Transaction.id == tx_id).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


class ReviewConflictsPaginationRegressionTests(unittest.TestCase):
    def test_same_category_conflicts_are_filtered_before_pagination(self):
        user_id = get_or_create_test_user()
        bank_name = f"ConflictPageBank-{uuid4().hex[:8]}"

        db = SessionLocal()
        kept_id: str | None = None
        try:
            filtered_tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 5),
                description="Filtered same-category conflict",
                merchant="Filtered Merchant",
                amount=Decimal("-10.00"),
                currency="USD",
                category="Shopping",
                bank_name=bank_name,
                review_status="conflict",
                review_category="shopping",
                created_at=datetime.now(timezone.utc),
            )
            kept_tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 4),
                description="Actual conflict after filtered row",
                merchant="Kept Merchant",
                amount=Decimal("-20.00"),
                currency="USD",
                category="Shopping",
                bank_name=bank_name,
                review_status="conflict",
                review_category="Food & Groceries",
                created_at=datetime.now(timezone.utc),
            )
            db.add_all([filtered_tx, kept_tx])
            db.commit()
            db.refresh(kept_tx)
            kept_id = str(kept_tx.id)
        finally:
            db.close()

        try:
            query_string = urlencode({
                "bank_name": bank_name,
                "limit": 1,
                "offset": 0,
            }).encode("utf-8")
            request = Request({
                "type": "http",
                "method": "GET",
                "path": "/api/transactions/review-conflicts",
                "query_string": query_string,
                "headers": [],
            })
            response = asyncio.run(get_review_conflicts(request))
            response_body = response.body.decode("utf-8")
            self.assertEqual(response.status_code, 200, response_body)
            payload = json.loads(response.body)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(len(payload["transactions"]), 1)
            self.assertEqual(payload["transactions"][0]["id"], kept_id)
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


class ReviewQueueFilteringRegressionTests(unittest.TestCase):
    def test_review_queue_excludes_rule_based_and_tiny_recurring_rows(self):
        user_id = get_or_create_test_user()
        bank_name = f"QueueFilterBank-{uuid4().hex[:8]}"
        since_dt = datetime.now(timezone.utc) - timedelta(days=1)
        created_at = datetime.now(timezone.utc)

        db = SessionLocal()
        manual_tx_id: str | None = None
        try:
            txs = [
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 5),
                    description="Tiny recurring",
                    merchant="Tiny recurring",
                    amount=Decimal("-5.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 4),
                    description="Tiny recurring",
                    merchant="Tiny recurring",
                    amount=Decimal("-5.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 3),
                    description="Tiny recurring",
                    merchant="Tiny recurring",
                    amount=Decimal("-5.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 5),
                    description="Monthly app subscription",
                    merchant="Monthly app subscription",
                    amount=Decimal("-12.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 4),
                    description="Monthly app subscription",
                    merchant="Monthly app subscription",
                    amount=Decimal("-12.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 3),
                    description="Monthly app subscription",
                    merchant="Monthly app subscription",
                    amount=Decimal("-12.00"),
                    currency="USD",
                    category="Other",
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 5),
                    description="Large rule assignment",
                    merchant="Large rule assignment",
                    amount=Decimal("-1000.00"),
                    currency="USD",
                    category="Shopping",
                    category_source="rule",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
                Transaction(
                    user_id=user_id,
                    date=date(2026, 3, 5),
                    description="Small manual PLN",
                    merchant="Small manual PLN",
                    amount=Decimal("-9.00"),
                    currency="PLN",
                    category=MANUAL_REVIEW,
                    category_source="ai",
                    bank_name=bank_name,
                    created_at=created_at,
                ),
            ]
            db.add_all(txs)
            db.commit()
            db.refresh(txs[-1])
            manual_tx_id = str(txs[-1].id)
        finally:
            db.close()

        try:
            query_string = urlencode({
                "bank_name": bank_name,
                "since": since_dt.isoformat(),
            }).encode("utf-8")
            request = Request({
                "type": "http",
                "method": "GET",
                "path": "/api/transactions/review-queue",
                "query_string": query_string,
                "headers": [],
            })
            response = asyncio.run(get_review_queue(request))
            response_body = response.body.decode("utf-8")
            self.assertEqual(response.status_code, 200, response_body)
            payload = json.loads(response.body)

            descriptions = [tx["description"] for tx in payload["transactions"]]
            self.assertNotIn("Tiny recurring", descriptions)
            self.assertNotIn("Large rule assignment", descriptions)
            self.assertNotIn("Small manual PLN", descriptions)
            self.assertEqual(len(payload["transactions"]), 3)
            self.assertTrue(all(tx["review_priority"] == "recurring" for tx in payload["transactions"]))
            self.assertTrue(all(abs(tx["amount"]) == 12.0 for tx in payload["transactions"]))

            verify_db = SessionLocal()
            try:
                refreshed = verify_db.query(Transaction).filter(Transaction.id == manual_tx_id).one()
                self.assertEqual(refreshed.category, "Other")
                self.assertEqual(refreshed.category_source, "ai")
            finally:
                verify_db.close()
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


class RuleAnalysisBackfillRegressionTests(unittest.TestCase):
    @patch("app.services.rule_analysis_service._validate_findings_with_llm", return_value=None)
    def test_rule_analysis_reapplies_new_rules_to_manual_review_transactions(self, _mock_llm_validation):
        user_id = get_or_create_test_user()
        bank_name = f"RuleBackfillBank-{uuid4().hex[:8]}"

        db = SessionLocal()
        tx_id: str | None = None
        try:
            tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 5),
                description="K001G54307",
                merchant="K001G54307",
                amount=Decimal("-42.00"),
                currency="USD",
                category=MANUAL_REVIEW,
                category_source="ai",
                bank_name=bank_name,
                created_at=datetime.now(timezone.utc),
            )
            rule = CategorizationPreference(
                user_id=user_id,
                bank_name=bank_name,
                name="Backfill K001G54307",
                rule={
                    "description_pattern": "K001G54307",
                    "category": "Shopping",
                },
                priority=10,
                enabled=True,
                preference_type="categorization",
            )
            db.add_all([tx, rule])
            db.commit()
            db.refresh(tx)
            tx_id = str(tx.id)
        finally:
            db.close()

        try:
            _findings, summary = analyze_rules_for_user(
                user_id=user_id,
                scope_since=date(2026, 1, 1),
            )

            self.assertGreaterEqual(summary["rule_backfill_updated"], 1)
            self.assertGreaterEqual(summary["rule_backfill_manual_resolved"], 1)

            verify_db = SessionLocal()
            try:
                refreshed = verify_db.query(Transaction).filter(Transaction.id == tx_id).first()
                self.assertIsNotNone(refreshed)
                self.assertEqual(refreshed.category, "Shopping")
                self.assertEqual(refreshed.category_source, "rule")
                self.assertIsNone(refreshed.review_category)
            finally:
                verify_db.close()
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.query(CategorizationPreference).filter(
                    CategorizationPreference.user_id == user_id,
                    CategorizationPreference.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()

    @patch("app.services.rule_analysis_service._validate_findings_with_llm", return_value=None)
    def test_rule_analysis_detects_conflicting_duplicate_matchers_without_transactions(self, _mock_llm_validation):
        user_id = get_or_create_test_user()
        bank_name = f"RuleAuditBank-{uuid4().hex[:8]}"

        db = SessionLocal()
        try:
            db.add_all([
                CategorizationPreference(
                    user_id=user_id,
                    bank_name=bank_name,
                    name="Google Generic Entertainment",
                    rule={"description_pattern": "Google", "category": "Entertainment"},
                    priority=1,
                    enabled=True,
                    preference_type="categorization",
                ),
                CategorizationPreference(
                    user_id=user_id,
                    bank_name=bank_name,
                    name="Google Generic Internal",
                    rule={"description_pattern": "Google", "category": "Internal Transfers"},
                    priority=0,
                    enabled=True,
                    preference_type="categorization",
                ),
            ])
            db.commit()
        finally:
            db.close()

        try:
            findings, summary = analyze_rules_for_user(
                user_id=user_id,
                scope_since=date(2026, 1, 1),
            )

            exact_conflicts = [
                finding for finding in findings
                if finding.finding_type == "rule_fix"
                and finding.payload.get("operation") == "merge"
                and "same matcher" in str(finding.payload.get("reason") or "").lower()
            ]
            self.assertTrue(exact_conflicts, "expected exact conflicting matcher finding")
            self.assertGreaterEqual(summary["rules_exact_conflicts"], 1)
            self.assertGreaterEqual(summary["rule_fix"], 1)
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(CategorizationPreference).filter(
                    CategorizationPreference.user_id == user_id,
                    CategorizationPreference.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()

    @patch("app.services.rule_analysis_service._validate_findings_with_llm", return_value=None)
    def test_rule_analysis_prefers_specific_rule_and_suggests_priority_fix(self, _mock_llm_validation):
        user_id = get_or_create_test_user()
        bank_name = f"RulePriorityBank-{uuid4().hex[:8]}"

        db = SessionLocal()
        tx_id: str | None = None
        specific_rule_id: str | None = None
        try:
            specific_rule = CategorizationPreference(
                user_id=user_id,
                bank_name=bank_name,
                name="Google Pay deposit specific",
                rule={"description_pattern": r"Google Pay deposit by \*1802", "category": "Internal Transfers"},
                priority=0,
                enabled=True,
                preference_type="categorization",
            )
            broad_rule = CategorizationPreference(
                user_id=user_id,
                bank_name=bank_name,
                name="Google generic",
                rule={"description_pattern": "Google", "category": "Entertainment"},
                priority=0,
                enabled=True,
                preference_type="categorization",
            )
            tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 5),
                description="Google Pay deposit by *1802",
                merchant="Google",
                amount=Decimal("42.00"),
                currency="USD",
                category="Entertainment",
                category_source="rule",
                bank_name=bank_name,
                created_at=datetime.now(timezone.utc),
            )
            db.add_all([specific_rule, broad_rule, tx])
            db.commit()
            db.refresh(tx)
            db.refresh(specific_rule)
            tx_id = str(tx.id)
            specific_rule_id = str(specific_rule.id)
        finally:
            db.close()

        try:
            findings, summary = analyze_rules_for_user(
                user_id=user_id,
                scope_since=date(2026, 1, 1),
            )

            tx_conflicts = [
                finding for finding in findings
                if finding.finding_type == "tx_conflict"
                and finding.payload.get("transaction_id") == tx_id
            ]
            self.assertTrue(tx_conflicts, "expected tx conflict for shadowed specific rule")
            self.assertEqual(tx_conflicts[0].payload.get("suggested_category"), "Internal Transfers")

            priority_fixes = [
                finding for finding in findings
                if finding.finding_type == "rule_fix"
                and finding.payload.get("operation") == "set_priority"
                and finding.payload.get("rule_id") == specific_rule_id
            ]
            self.assertTrue(priority_fixes, "expected priority fix for specific rule")
            self.assertGreaterEqual(summary["rule_fix"], 1)
        finally:
            cleanup_db = SessionLocal()
            try:
                cleanup_db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.bank_name == bank_name,
                ).delete()
                cleanup_db.query(CategorizationPreference).filter(
                    CategorizationPreference.user_id == user_id,
                    CategorizationPreference.bank_name == bank_name,
                ).delete()
                cleanup_db.commit()
            finally:
                cleanup_db.close()


if __name__ == "__main__":
    unittest.main()
