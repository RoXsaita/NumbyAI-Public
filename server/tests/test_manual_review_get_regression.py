#!/usr/bin/env python3

import asyncio
import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

from starlette.requests import Request

from app.database import SessionLocal, Transaction, get_or_create_test_user
from app.main import get_manual_review_transactions
from app.tools.category_helpers import MANUAL_REVIEW


class ManualReviewGetRegressionTests(unittest.TestCase):
    def test_get_endpoint_does_not_mutate_small_manual_review_rows(self):
        user_id = get_or_create_test_user()
        bank_name = f"ManualReviewGet-{uuid4().hex[:8]}"

        db = SessionLocal()
        tx_id: str | None = None
        try:
            tx = Transaction(
                user_id=user_id,
                date=date(2026, 3, 5),
                description="Small manual PLN",
                merchant="Small manual PLN",
                amount=Decimal("-19.99"),
                currency="PLN",
                category=MANUAL_REVIEW,
                category_source="ai",
                bank_name=bank_name,
                created_at=datetime.now(timezone.utc),
            )
            db.add(tx)
            db.commit()
            db.refresh(tx)
            tx_id = str(tx.id)
        finally:
            db.close()

        try:
            query_string = urlencode({"bank_name": bank_name}).encode("utf-8")
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/api/transactions/manual-review",
                    "query_string": query_string,
                    "headers": [],
                }
            )

            response = asyncio.run(get_manual_review_transactions(request))
            self.assertEqual(response.status_code, 200, response.body.decode("utf-8"))
            payload = json.loads(response.body)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["transactions"][0]["category"], MANUAL_REVIEW)

            verify_db = SessionLocal()
            try:
                refreshed = verify_db.query(Transaction).filter(Transaction.id == tx_id).one()
                self.assertEqual(refreshed.category, MANUAL_REVIEW)
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


if __name__ == "__main__":
    unittest.main()
