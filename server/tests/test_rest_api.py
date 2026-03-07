#!/usr/bin/env python3
"""
REST API Integration Test Script
Tests all REST API endpoints to ensure they work correctly after refactor.
"""
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pytest
import requests

# Add parent directory to path
sys.path.insert(0, '.')

BASE_URL = "http://localhost:8000"

pytestmark = pytest.mark.skip(
    reason="Manual integration suite. Run `python tests/test_rest_api.py` with the server running."
)


class ApiTestResult:
    def __init__(self, endpoint: str, method: str, status: str, response_summary: str, notes: str = ""):
        self.endpoint = endpoint
        self.method = method
        self.status = status
        self.response_summary = response_summary
        self.notes = notes


# Global test state
test_results: List[ApiTestResult] = []


def run_api_test(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict] = None,
    files: Optional[Dict] = None,
) -> ApiTestResult:
    """Run an API test and record results"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        elif method == "POST":
            if files:
                response = requests.post(url, data=data, files=files, timeout=10)
            else:
                response = requests.post(url, json=data, timeout=5)
        elif method == "PATCH":
            response = requests.patch(url, json=data, timeout=5)
        else:
            return ApiTestResult(endpoint, method, "error", f"Unsupported method: {method}")
        
        status_code = response.status_code
        try:
            response_data = response.json()
            response_summary = f"Status {status_code}: {str(response_data)[:200]}"
        except ValueError:
            response_summary = f"Status {status_code}: {response.text[:200]}"
        
        if 200 <= status_code < 300:
            status = "pass"
        elif 400 <= status_code < 500:
            status = "fail"
        else:
            status = "error"
        
        result = ApiTestResult(endpoint, method, status, response_summary)
        test_results.append(result)
        return result

    except requests.exceptions.ConnectionError:
        result = ApiTestResult(endpoint, method, "error", "Connection refused - server not running")
        test_results.append(result)
        return result
    except Exception as e:
        result = ApiTestResult(endpoint, method, "error", f"Exception: {str(e)}")
        test_results.append(result)
        return result


def test_health():
    """Test health check endpoint"""
    print("\n" + "="*60)
    print("Testing GET /health")
    print("="*60)
    result = run_api_test("/health", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary}")
    return result


def test_financial_data():
    """Test financial data endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/financial-data")
    print("="*60)
    result = run_api_test("/api/financial-data", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_transactions_get():
    """Test transactions GET endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/transactions")
    print("="*60)
    result = run_api_test("/api/transactions", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_transactions_patch():
    """Test transactions PATCH endpoint"""
    print("\n" + "="*60)
    print("Testing PATCH /api/transactions")
    print("="*60)
    # This will likely fail without a real transaction ID, but tests the endpoint
    data = {
        "id": "test-id-123",
        "updates": {"category": "Food & Groceries"}
    }
    result = run_api_test("/api/transactions", "PATCH", data=data)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_budgets_get():
    """Test budgets GET endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/budgets")
    print("="*60)
    result = run_api_test("/api/budgets", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_budgets_post():
    """Test budgets POST endpoint"""
    print("\n" + "="*60)
    print("Testing POST /api/budgets")
    print("="*60)
    data = {
        "budgets": [
            {
                "category": "Food & Groceries",
                "month_year": "2024-12",
                "amount": 500.0,
                "currency": "USD"
            }
        ]
    }
    result = run_api_test("/api/budgets", "POST", data=data)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_preferences_get():
    """Test preferences GET endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/preferences")
    print("="*60)
    result = run_api_test("/api/preferences", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_preferences_post():
    """Test preferences POST endpoint"""
    print("\n" + "="*60)
    print("Testing POST /api/preferences")
    print("="*60)
    data = {
        "preferences": [
            {
                "name": "Test Preference",
                "rule": {
                    "conditions": {"merchant": "TEST"},
                    "category": "Shopping"
                }
            }
        ],
        "preference_type": "categorization"
    }
    result = run_api_test("/api/preferences", "POST", data=data)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_statements_upload():
    """Test statement upload endpoint"""
    print("\n" + "="*60)
    print("Testing POST /api/statements/upload")
    print("="*60)
    # Create a dummy CSV file
    import io
    csv_content = "Date,Description,Amount\n2024-01-01,Test Transaction,100.00"
    files = {
        'file': ('test.csv', io.BytesIO(csv_content.encode()), 'text/csv')
    }
    data = {
        'bank_name': 'Test Bank',
        'net_flow': '100.00'
    }
    result = run_api_test("/api/statements/upload", "POST", data=data, files=files)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_auth_register():
    """Test auth register endpoint"""
    print("\n" + "="*60)
    print("Testing POST /api/auth/register")
    print("="*60)
    data = {
        "email": f"test_{datetime.now().timestamp()}@example.com",
        "name": "Test User",
        "password": "testpass123"
    }
    result = run_api_test("/api/auth/register", "POST", data=data)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_auth_login():
    """Test auth login endpoint"""
    print("\n" + "="*60)
    print("Testing POST /api/auth/login")
    print("="*60)
    data = {
        "email": "test@local.dev",
        "password": "testpass"
    }
    result = run_api_test("/api/auth/login", "POST", data=data)
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def test_auth_me():
    """Test auth me endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/auth/me")
    print("="*60)
    result = run_api_test("/api/auth/me", "GET")
    print(f"Status: {result.status.upper()}")
    print(f"Response: {result.response_summary[:300]}")
    return result


def main():
    """Run all API tests"""
    print("="*60)
    print("REST API Integration Tests")
    print("="*60)
    print(f"Testing against: {BASE_URL}")
    print("Note: Server must be running for these tests to work")
    
    # Test all endpoints
    test_health()
    test_financial_data()
    test_transactions_get()
    test_transactions_patch()
    test_budgets_get()
    test_budgets_post()
    test_preferences_get()
    test_preferences_post()
    test_statements_upload()
    test_auth_register()
    test_auth_login()
    test_auth_me()
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    total = len(test_results)
    passed = len([r for r in test_results if r.status == "pass"])
    failed = len([r for r in test_results if r.status == "fail"])
    errors = len([r for r in test_results if r.status == "error"])
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: {errors}")
    
    if errors > 0:
        print("\nErrors (likely server not running):")
        for r in test_results:
            if r.status == "error":
                print(f"  {r.method} {r.endpoint}: {r.response_summary[:100]}")
    
    return 0 if (failed == 0 and errors == 0) else 1


if __name__ == "__main__":
    exit(main())
