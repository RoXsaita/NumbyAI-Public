#!/usr/bin/env python3
"""
QA Test Script for Categorization Preferences Tools
Tests fetch_categorization_preferences and save_categorization_preferences
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, '.')

from app.tools.fetch_preferences import fetch_preferences_handler
from app.tools.save_preferences import save_preferences_handler
from app.database import SessionLocal, CategorizationPreference, resolve_user_id


class TestResult:
    __test__ = False

    def __init__(self, test_case: str, status: str, tool: str, request: Dict, 
                 response_summary: str, notes: str = ""):
        self.test_case = test_case
        self.status = status
        self.tool = tool
        self.request = request
        self.response_summary = response_summary
        self.notes = notes


class Finding:
    def __init__(self, id: int, priority: str, component: str, summary: str,
                 problem: str, expected: str, actual: str, solution: str = ""):
        self.id = id
        self.priority = priority
        self.component = component
        self.summary = summary
        self.problem = problem
        self.expected = expected
        self.actual = actual
        self.solution = solution


# Global test state
test_results: List[TestResult] = []
findings: List[Finding] = []
finding_id_counter = 1


def clean_database():
    """Clean all preferences for test user"""
    db = SessionLocal()
    try:
        user_id = resolve_user_id(None)
        db.query(CategorizationPreference).filter(
            CategorizationPreference.user_id == user_id
        ).delete()
        db.commit()
    except Exception as e:
        print(f"Error cleaning database: {e}")
        db.rollback()
    finally:
        db.close()


async def run_test(test_name: str, tool_name: str, func, *args, **kwargs):
    """Run a test and record results"""
    global test_results, findings, finding_id_counter
    
    print(f"\n{'='*60}")
    print(f"Running {test_name}")
    print(f"{'='*60}")
    
    try:
        result = await func(*args, **kwargs)
        
        # Extract response summary
        if "structuredContent" in result:
            sc = result["structuredContent"]
            if "error" in sc or "errors" in sc:
                status = "fail"
                response_summary = f"Error: {sc.get('error', sc.get('errors', 'Unknown error'))}"
            elif "preferences" in sc:
                count = sc.get("count", len(sc.get("preferences", [])))
                response_summary = f"Returned {count} preferences"
                status = "pass"
            elif "results" in sc:
                summary = sc.get("summary", {})
                response_summary = f"Created: {summary.get('created', 0)}, Updated: {summary.get('updated', 0)}, Errors: {summary.get('errors', 0)}"
                status = "pass" if summary.get("errors", 0) == 0 else "fail"
            else:
                response_summary = str(sc)
                status = "pass"
        else:
            response_summary = "Unexpected response format"
            status = "error"
        
        test_results.append(TestResult(
            test_case=test_name,
            status=status,
            tool=tool_name,
            request={"summary": str(kwargs)},
            response_summary=response_summary,
            notes=""
        ))
        
        print(f"Status: {status.upper()}")
        print(f"Response: {response_summary}")
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: {error_msg}")
        test_results.append(TestResult(
            test_case=test_name,
            status="error",
            tool=tool_name,
            request={"summary": str(kwargs)},
            response_summary=f"Exception: {error_msg}",
            notes=""
        ))
        return None


async def tc1_fetch_empty():
    """TC1: Fetch Empty Preferences"""
    global finding_id_counter
    clean_database()
    result = await run_test(
        "TC1",
        "fetch_categorization_preferences",
        fetch_preferences_handler,
        user_id=None
    )
    
    if result and "structuredContent" in result:
        sc = result["structuredContent"]
        if sc.get("count", -1) == 0:
            print("✓ Correctly returned empty array")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P3",
                component="fetch_categorization_preferences",
                summary="Empty fetch returned non-zero count",
                problem="When no preferences exist, count should be 0",
                actual=f"Count was {sc.get('count', 'missing')}",
                expected="count: 0"
            ))
            finding_id_counter += 1


async def tc2_save_single():
    """TC2: Save Single Preference"""
    global finding_id_counter
    clean_database()
    
    # Save
    save_result = await run_test(
        "TC2-Save",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Netflix to Entertainment",
            "rule": {
                "conditions": {"merchant": "NETFLIX"},
                "category": "Entertainment"
            }
        }],
        user_id=None
    )
    
    if save_result and "structuredContent" in save_result:
        sc = save_result["structuredContent"]
        if sc.get("summary", {}).get("created", 0) == 1:
            print("✓ Successfully saved preference")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P1",
                component="save_categorization_preferences",
                summary="Failed to save single preference",
                problem="Save operation did not create preference",
                actual=f"Created: {sc.get('summary', {}).get('created', 0)}",
                expected="created: 1"
            ))
            finding_id_counter += 1
    
    # Fetch and verify
    fetch_result = await run_test(
        "TC2-Fetch",
        "fetch_categorization_preferences",
        fetch_preferences_handler,
        user_id=None
    )
    
    if fetch_result and "structuredContent" in fetch_result:
        sc = fetch_result["structuredContent"]
        prefs = sc.get("preferences", [])
        if len(prefs) == 1 and prefs[0]["name"] == "Netflix to Entertainment":
            print("✓ Successfully fetched saved preference")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P1",
                component="fetch_categorization_preferences",
                summary="Failed to fetch saved preference",
                problem="Saved preference not returned by fetch",
                actual=f"Found {len(prefs)} preferences",
                expected="1 preference with name 'Netflix to Entertainment'"
            ))
            finding_id_counter += 1


async def tc3_save_multiple():
    """TC3: Save Multiple Preferences"""
    global finding_id_counter
    clean_database()
    
    prefs_to_save = [
        {"name": "Uber", "rule": {"conditions": {"merchant": "UBER"}, "category": "Transportation"}},
        {"name": "Spotify", "rule": {"conditions": {"merchant": "SPOTIFY"}, "category": "Entertainment"}},
        {"name": "Amazon", "rule": {"conditions": {"merchant": "AMAZON"}, "category": "Shopping"}}
    ]
    
    save_result = await run_test(
        "TC3-Save",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=prefs_to_save,
        user_id=None
    )
    
    if save_result and "structuredContent" in save_result:
        sc = save_result["structuredContent"]
        created = sc.get("summary", {}).get("created", 0)
        if created == 3:
            print("✓ Successfully saved all 3 preferences")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="save_categorization_preferences",
                summary="Batch save incomplete",
                problem="Not all preferences were saved",
                actual=f"Created: {created}",
                expected="created: 3"
            ))
            finding_id_counter += 1
    
    # Fetch and verify
    fetch_result = await run_test(
        "TC3-Fetch",
        "fetch_categorization_preferences",
        fetch_preferences_handler,
        user_id=None
    )
    
    if fetch_result and "structuredContent" in fetch_result:
        sc = fetch_result["structuredContent"]
        prefs = sc.get("preferences", [])
        if len(prefs) == 3:
            names = {p["name"] for p in prefs}
            expected_names = {"Uber", "Spotify", "Amazon"}
            if names == expected_names:
                print("✓ Successfully fetched all 3 preferences")
            else:
                findings.append(Finding(
                    id=finding_id_counter,
                    priority="P2",
                    component="fetch_categorization_preferences",
                    summary="Missing preferences in fetch",
                    problem="Not all saved preferences returned",
                    actual=f"Names: {names}",
                    expected=f"Names: {expected_names}"
                ))
                finding_id_counter += 1
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="fetch_categorization_preferences",
                summary="Wrong count in fetch",
                problem="Fetch returned wrong number of preferences",
                actual=f"Count: {len(prefs)}",
                expected="Count: 3"
            ))
            finding_id_counter += 1


async def tc4_update_existing():
    """TC4: Update Existing Preference"""
    global finding_id_counter
    clean_database()
    
    # Save initial preference
    await save_preferences_handler(
        preferences=[{
            "name": "Uber",
            "rule": {
                "conditions": {"merchant": "UBER"},
                "category": "Transportation"
            }
        }],
        user_id=None
    )
    
    # Fetch to get ID
    fetch1 = await fetch_preferences_handler(user_id=None)
    pref_id = None
    if fetch1 and "structuredContent" in fetch1:
        prefs = fetch1["structuredContent"].get("preferences", [])
        if prefs:
            pref_id = prefs[0]["id"]
    
    if not pref_id:
        findings.append(Finding(
            id=finding_id_counter,
            priority="P2",
            component="fetch_categorization_preferences",
            summary="Cannot get preference ID for update test",
            problem="Need preference ID to test update",
            actual="No ID returned",
            expected="ID in preference object"
        ))
        finding_id_counter += 1
        return
    
    # Try to update by saving same merchant with different category
    # Note: The current implementation doesn't dedupe by merchant, so we need to use preference_id
    update_result = await run_test(
        "TC4-Update",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "preference_id": pref_id,
            "name": "Uber",
            "rule": {
                "conditions": {"merchant": "UBER"},
                "category": "Shopping"
            }
        }],
        user_id=None
    )
    
    if update_result and "structuredContent" in update_result:
        sc = update_result["structuredContent"]
        updated = sc.get("summary", {}).get("updated", 0)
        if updated == 1:
            print("✓ Successfully updated preference")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="save_categorization_preferences",
                summary="Update did not work",
                problem="Preference update did not update existing record",
                actual=f"Updated: {updated}",
                expected="updated: 1"
            ))
            finding_id_counter += 1
    
    # Verify update
    fetch2 = await fetch_preferences_handler(user_id=None)
    if fetch2 and "structuredContent" in fetch2:
        prefs = fetch2["structuredContent"].get("preferences", [])
        if len(prefs) == 1 and prefs[0]["rule"]["category"] == "Shopping":
            print("✓ Update verified - category changed to Shopping")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="save_categorization_preferences",
                summary="Update not persisted",
                problem="Category did not change after update",
                actual=f"Category: {prefs[0]['rule']['category'] if prefs else 'N/A'}",
                expected="Category: Shopping"
            ))
            finding_id_counter += 1


async def tc5_invalid_category():
    """TC5: Invalid Category in Preference"""
    global finding_id_counter
    clean_database()
    
    result = await run_test(
        "TC5",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Test",
            "rule": {
                "conditions": {"merchant": "TEST"},
                "category": "InvalidCategory"
            }
        }],
        user_id=None
    )
    
    if result and "structuredContent" in result:
        sc = result["structuredContent"]
        if "errors" in sc:
            errors = sc["errors"]
            if any("Invalid category" in str(e) for e in errors):
                print("✓ Correctly rejected invalid category")
            else:
                findings.append(Finding(
                    id=finding_id_counter,
                    priority="P1",
                    component="save_categorization_preferences",
                    summary="Invalid category validation missing",
                    problem="Should reject invalid category",
                    actual=f"Errors: {errors}",
                    expected="Error mentioning 'Invalid category'"
                ))
                finding_id_counter += 1
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P1",
                component="save_categorization_preferences",
                summary="Invalid category accepted",
                problem="Should reject invalid category",
                actual="No validation error",
                expected="Validation error for invalid category"
            ))
            finding_id_counter += 1


async def tc6_missing_fields():
    """TC6: Missing Required Fields"""
    global finding_id_counter
    clean_database()
    
    # Test missing name
    result1 = await run_test(
        "TC6-NoName",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "rule": {
                "conditions": {"merchant": "TEST"},
                "category": "Shopping"
            }
        }],
        user_id=None
    )
    
    if result1 and "structuredContent" in result1:
        sc = result1["structuredContent"]
        if "errors" in sc:
            errors = sc["errors"]
            if any("missing required 'name'" in str(e).lower() for e in errors):
                print("✓ Correctly rejected missing name")
            else:
                findings.append(Finding(
                    id=finding_id_counter,
                    priority="P1",
                    component="save_categorization_preferences",
                    summary="Missing name validation unclear",
                    problem="Should clearly indicate missing name field",
                    actual=f"Errors: {errors}",
                    expected="Error mentioning 'missing required name'"
                ))
                finding_id_counter += 1
    
    # Test missing rule
    result2 = await run_test(
        "TC6-NoRule",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Test"
        }],
        user_id=None
    )
    
    if result2 and "structuredContent" in result2:
        sc = result2["structuredContent"]
        if "errors" in sc:
            errors = sc["errors"]
            if any("missing required 'rule'" in str(e).lower() for e in errors):
                print("✓ Correctly rejected missing rule")
            else:
                findings.append(Finding(
                    id=finding_id_counter,
                    priority="P1",
                    component="save_categorization_preferences",
                    summary="Missing rule validation unclear",
                    problem="Should clearly indicate missing rule field",
                    actual=f"Errors: {errors}",
                    expected="Error mentioning 'missing required rule'"
                ))
                finding_id_counter += 1
    
    # Test missing conditions
    result3 = await run_test(
        "TC6-NoConditions",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Test",
            "rule": {
                "category": "Shopping"
            }
        }],
        user_id=None
    )
    
    # Note: Conditions are optional in the schema, so this might pass
    # But let's check if it does
    if result3 and "structuredContent" in result3:
        sc = result3["structuredContent"]
        if "errors" not in sc:
            print("✓ Conditions are optional (no error)")
        else:
            print("✓ Conditions validation exists")


async def tc7_bank_specific():
    """TC7: Bank-Specific Preference"""
    clean_database()
    
    save_result = await run_test(
        "TC7-Save",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Chase Specific Rule",
            "rule": {
                "conditions": {"merchant": "CHASE"},
                "category": "Other"
            },
            "bank_name": "Chase"
        }],
        user_id=None
    )
    
    if save_result and "structuredContent" in save_result:
        sc = save_result["structuredContent"]
        if sc.get("summary", {}).get("created", 0) == 1:
            print("✓ Successfully saved bank-specific preference")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="save_categorization_preferences",
                summary="Failed to save bank-specific preference",
                problem="Bank-specific preference not saved",
                actual=f"Created: {sc.get('summary', {}).get('created', 0)}",
                expected="created: 1"
            ))
            finding_id_counter += 1
    
    # Fetch and verify bank association
    fetch_result = await fetch_preferences_handler(user_id=None)
    if fetch_result and "structuredContent" in fetch_result:
        prefs = fetch_result["structuredContent"].get("preferences", [])
        bank_prefs = [p for p in prefs if p.get("bank_name") == "Chase"]
        if len(bank_prefs) == 1:
            print("✓ Bank association verified")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P2",
                component="fetch_categorization_preferences",
                summary="Bank association not preserved",
                problem="Bank name not returned in fetch",
                actual=f"Found {len(bank_prefs)} Chase preferences",
                expected="1 preference with bank_name='Chase'"
            ))
            finding_id_counter += 1


async def tc8_case_sensitivity():
    """TC8: Case Sensitivity"""
    global finding_id_counter
    clean_database()
    
    # Save with lowercase
    await save_preferences_handler(
        preferences=[{
            "name": "Lowercase Test",
            "rule": {
                "conditions": {"merchant": "uber"},
                "category": "Transportation"
            }
        }],
        user_id=None
    )
    
    # Fetch and check
    fetch_result = await fetch_preferences_handler(user_id=None)
    if fetch_result and "structuredContent" in fetch_result:
        prefs = fetch_result["structuredContent"].get("preferences", [])
        if prefs:
            merchant = prefs[0]["rule"]["conditions"].get("merchant", "")
            print(f"✓ Merchant stored as: '{merchant}'")
            # Note: Actual matching behavior would need to be tested in categorization logic
            # This just verifies storage


async def tc9_special_characters():
    """TC9: Special Characters in Merchant"""
    global finding_id_counter
    clean_database()
    
    special_merchants = ["MCDONALD'S", "AT&T", "7-ELEVEN"]
    
    save_result = await run_test(
        "TC9",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[
            {
                "name": f"Test {m}",
                "rule": {
                    "conditions": {"merchant": m},
                    "category": "Other"
                }
            }
            for m in special_merchants
        ],
        user_id=None
    )
    
    if save_result and "structuredContent" in save_result:
        sc = save_result["structuredContent"]
        created = sc.get("summary", {}).get("created", 0)
        if created == 3:
            print("✓ Successfully saved preferences with special characters")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P3",
                component="save_categorization_preferences",
                summary="Special characters handling issue",
                problem="May have issues with special characters in merchant names",
                actual=f"Created: {created}",
                expected="created: 3"
            ))
            finding_id_counter += 1


async def tc10_long_merchant_name():
    """TC10: Long Merchant Name"""
    global finding_id_counter
    clean_database()
    
    long_name = "A" * 150  # 150 characters
    
    result = await run_test(
        "TC10",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Long Merchant Test",
            "rule": {
                "conditions": {"merchant": long_name},
                "category": "Other"
            }
        }],
        user_id=None
    )
    
    if result and "structuredContent" in result:
        sc = result["structuredContent"]
        if "errors" not in sc and sc.get("summary", {}).get("created", 0) == 1:
            print("✓ Long merchant name accepted")
        elif "errors" in sc:
            print("⚠ Long merchant name rejected (may be intentional)")
        else:
            findings.append(Finding(
                id=finding_id_counter,
                priority="P4",
                component="save_categorization_preferences",
                summary="Long merchant name handling unclear",
                problem="Behavior with very long merchant names",
                actual="Unclear",
                expected="Either accept or reject with clear error"
            ))
            finding_id_counter += 1


async def tc11_empty_conditions():
    """TC11: Empty Conditions"""
    global finding_id_counter
    clean_database()
    
    result = await run_test(
        "TC11",
        "save_categorization_preferences",
        save_preferences_handler,
        preferences=[{
            "name": "Empty Conditions Test",
            "rule": {
                "conditions": {},
                "category": "Other"
            }
        }],
        user_id=None
    )
    
    if result and "structuredContent" in result:
        sc = result["structuredContent"]
        if "errors" not in sc:
            print("✓ Empty conditions accepted (may match everything)")
        else:
            print("⚠ Empty conditions rejected")


async def tc12_preference_ordering():
    """TC12: Preference Ordering"""
    global finding_id_counter
    clean_database()
    
    # Save multiple preferences with different priorities
    await save_preferences_handler(
        preferences=[
            {"name": "Low Priority", "rule": {"conditions": {"merchant": "TEST"}, "category": "Other"}, "priority": 1},
            {"name": "High Priority", "rule": {"conditions": {"merchant": "TEST"}, "category": "Shopping"}, "priority": 10},
            {"name": "Medium Priority", "rule": {"conditions": {"merchant": "TEST"}, "category": "Entertainment"}, "priority": 5},
        ],
        user_id=None
    )
    
    fetch_result = await fetch_preferences_handler(user_id=None)
    if fetch_result and "structuredContent" in fetch_result:
        prefs = fetch_result["structuredContent"].get("preferences", [])
        if len(prefs) == 3:
            priorities = [p.get("priority", 0) for p in prefs]
            # Should be sorted by priority desc (higher first)
            if priorities == sorted(priorities, reverse=True):
                print("✓ Preferences correctly ordered by priority")
            else:
                findings.append(Finding(
                    id=finding_id_counter,
                    priority="P3",
                    component="fetch_categorization_preferences",
                    summary="Preference ordering incorrect",
                    problem="Preferences should be ordered by priority (desc)",
                    actual=f"Priorities: {priorities}",
                    expected="Priorities: [10, 5, 1]"
                ))
                finding_id_counter += 1


async def main():
    """Run all test cases"""
    global test_results, findings
    
    print("="*60)
    print("QA Testing: Categorization Preferences Tools")
    print("="*60)
    
    # Clean database first
    print("\nCleaning database...")
    clean_database()
    
    # Run all test cases
    await tc1_fetch_empty()
    await tc2_save_single()
    await tc3_save_multiple()
    await tc4_update_existing()
    await tc5_invalid_category()
    await tc6_missing_fields()
    await tc7_bank_specific()
    await tc8_case_sensitivity()
    await tc9_special_characters()
    await tc10_long_merchant_name()
    await tc11_empty_conditions()
    await tc12_preference_ordering()
    
    # Generate report
    timestamp = datetime.now(timezone.utc).isoformat()
    
    report = {
        "agent": "tool-preferences",
        "timestamp": timestamp,
        "test_results": [
            {
                "test_case": tr.test_case,
                "status": tr.status,
                "tool": tr.tool,
                "request": tr.request,
                "response_summary": tr.response_summary,
                "notes": tr.notes
            }
            for tr in test_results
        ],
        "findings": [
            {
                "id": f.id,
                "priority": f.priority,
                "component": f.component,
                "summary": f.summary,
                "problem": f.problem,
                "expected": f.expected,
                "actual": f.actual,
                "solution": f.solution
            }
            for f in findings
        ],
        "tool_coverage": {
            "fetch_tested": any("fetch" in tr.tool for tr in test_results),
            "save_tested": any("save" in tr.tool for tr in test_results),
            "update_tested": any("TC4" in tr.test_case for tr in test_results),
            "validation_tested": any("TC5" in tr.test_case or "TC6" in tr.test_case for tr in test_results)
        }
    }
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    total_tests = len(test_results)
    passed = sum(1 for tr in test_results if tr.status == "pass")
    failed = sum(1 for tr in test_results if tr.status == "fail")
    errors = sum(1 for tr in test_results if tr.status == "error")
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Errors: {errors}")
    print(f"\nFindings: {len(findings)}")
    
    # Save report
    output_file = f"audit/raw/tool-preferences-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    import os
    os.makedirs("audit/raw", exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nReport saved to: {output_file}")
    
    # Print findings
    if findings:
        print("\n" + "="*60)
        print("FINDINGS")
        print("="*60)
        for finding in findings:
            print(f"\n[{finding.priority}] {finding.summary}")
            print(f"  Component: {finding.component}")
            print(f"  Problem: {finding.problem}")
            print(f"  Expected: {finding.expected}")
            print(f"  Actual: {finding.actual}")
            if finding.solution:
                print(f"  Solution: {finding.solution}")
    
    return report


if __name__ == "__main__":
    asyncio.run(main())
