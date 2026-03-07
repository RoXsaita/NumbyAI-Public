#!/usr/bin/env python3
"""
End-to-end categorization test.

Uploads a real Santander CSV via the streaming endpoint,
reads SSE events, and prints a quality report.

Exit 0 if "Other" ratio < 15 %, exit 1 otherwise.
"""
import glob
import json
import os
import sys
import requests

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000")
OTHER_THRESHOLD = 0.15


def check_llm():
    try:
        r = requests.get(f"{BACKEND}/health", timeout=5)
        r.raise_for_status()
        llm = r.json().get("llm", {})
        if llm.get("available"):
            return True
        print(f"SKIP: Configured LLM not available ({llm})")
        return False
    except Exception as e:
        print(f"SKIP: Unable to read backend LLM status ({e})")
        return False


def check_backend():
    try:
        r = requests.get(f"{BACKEND}/health", timeout=5)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"SKIP: Backend not reachable at {BACKEND} ({e})")
        return False


def find_santander_csv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.join(script_dir, "..", "uploads")
    pattern = os.path.join(uploads_dir, "**", "*Santander*January*.csv")
    matches = sorted(glob.glob(pattern, recursive=True))
    if not matches:
        print("SKIP: No Santander CSV found in uploads/")
        return None
    return matches[0]


def stream_upload(csv_path: str):
    url = f"{BACKEND}/api/statements/process-stream"
    with open(csv_path, "rb") as f:
        resp = requests.post(
            url,
            files={"file": (os.path.basename(csv_path), f, "text/csv")},
            data={"bank_name": "Santander"},
            stream=True,
            timeout=600,
        )
    resp.raise_for_status()

    events = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        events.append(payload)
        etype = payload.get("type", "")
        if etype == "stage":
            print(f"  [{etype}] {payload.get('name', '')} — txns: {payload.get('transactions', '-')}")
        elif etype == "categorization_start":
            print(f"  [{etype}] {payload.get('total_transactions')} txns in {payload.get('total_batches')} batches")
        elif etype == "categorization_progress":
            print(f"  [{etype}] batch {payload.get('batch_index')}/{payload.get('total_batches')} — {payload.get('categorized', 0)} categorized")
        elif etype == "categorization_complete":
            print(f"  [{etype}] {payload.get('categorized')} total categorized")
        elif etype == "categorization_warning":
            print(f"  [WARN] {payload.get('message', '')}")
        elif etype == "complete":
            print(f"  [complete] {payload.get('result', {}).get('message', 'done')}")
        elif etype == "error":
            print(f"  [ERROR] {payload.get('error', 'unknown')}")
        else:
            print(f"  [{etype}] {json.dumps(payload)[:120]}")

    return events


def fetch_transaction_breakdown():
    """Fetch category breakdown directly from the transactions API."""
    try:
        resp = requests.get(f"{BACKEND}/api/transactions", timeout=10)
        resp.raise_for_status()
        txns = resp.json().get("transactions", [])
        from collections import Counter
        return Counter(t.get("category", "Other") for t in txns), len(txns)
    except Exception:
        return {}, 0


def report(events):
    complete_evt = next((e for e in events if e.get("type") == "complete"), None)
    if not complete_evt:
        print("\nERROR: no 'complete' event received")
        return False

    result = complete_evt.get("result", {})
    total = result.get("transactions_processed", 0)
    print(f"\n{'='*60}")
    print(f"Total transactions processed: {total}")
    print(f"Categories: {result.get('categories', '?')}")
    print(f"{'='*60}")

    dashboard = result.get("dashboard", {})
    categories = dashboard.get("category_summaries", [])
    grand_total = sum(c.get("transaction_count", 0) for c in categories) if categories else 0

    if grand_total == 0:
        cat_counts, grand_total = fetch_transaction_breakdown()
        categories = [
            {"category": cat, "transaction_count": cnt}
            for cat, cnt in cat_counts.items()
        ]

    if not categories or grand_total == 0:
        print("FAIL — no category data available for validation")
        return False

    print(f"\n{'Category':<25} {'Count':>6}  {'%':>6}")
    print("-" * 42)
    other_count = 0
    for cat in sorted(categories, key=lambda c: c.get("transaction_count", 0), reverse=True):
        name = cat.get("category", "?")
        count = cat.get("transaction_count", 0)
        pct = (count / grand_total * 100) if grand_total else 0
        print(f"  {name:<23} {count:>6}  {pct:>5.1f}%")
        if name == "Other":
            other_count = count

    other_ratio = other_count / grand_total if grand_total else 0
    print(f"\n'Other' ratio: {other_ratio:.1%}  (threshold: {OTHER_THRESHOLD:.0%})")
    if other_ratio < OTHER_THRESHOLD:
        print("PASS")
        return True
    else:
        print("FAIL — too many transactions categorized as Other")
        return False


def main():
    print("=== E2E Categorization Test ===\n")

    if not check_llm():
        sys.exit(0)
    if not check_backend():
        sys.exit(0)

    csv_path = find_santander_csv()
    if not csv_path:
        sys.exit(0)

    print(f"Using CSV: {csv_path}\n")
    print("Streaming upload + categorization...\n")

    events = stream_upload(csv_path)
    passed = report(events)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
