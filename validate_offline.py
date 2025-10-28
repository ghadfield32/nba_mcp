"""
Offline Validation Script for NBA MCP

Tests functionality that doesn't require live NBA API calls:
1. Static data (players, teams)
2. Entity resolution (uses static data)
3. Response envelope structure
4. Schema versioning
5. Code structure and imports

This validation can run without hitting NBA API rate limits.
"""

import sys
import json
from typing import Dict, Any

sys.path.insert(0, "/home/user/nba_mcp")

from nba_api.stats.static import players, teams
from nba_mcp.api.entity_resolver import resolve_entity
from nba_mcp.api.models import (
    ResponseEnvelope,
    success_response,
    error_response,
    ResponseMetadata,
)
from nba_mcp.api.errors import EntityNotFoundError


class ValidationReport:
    """Track validation results."""

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def add_pass(self, test_name: str):
        self.tests_run += 1
        self.tests_passed += 1
        print(f"✅ {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.tests_run += 1
        self.tests_failed += 1
        self.failures.append({"test": test_name, "error": error})
        print(f"❌ {test_name}: {error}")

    def print_summary(self):
        print("\n" + "=" * 70)
        print("OFFLINE VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {self.tests_run}")
        print(
            f"Passed: {self.tests_passed} ({self.tests_passed/self.tests_run*100:.1f}%)"
        )
        print(
            f"Failed: {self.tests_failed} ({self.tests_failed/self.tests_run*100:.1f}%)"
        )

        if self.failures:
            print("\nFAILURES:")
            for failure in self.failures:
                print(f"  - {failure['test']}: {failure['error']}")
        else:
            print("\n🎉 ALL OFFLINE TESTS PASSED!")

        return self.tests_failed == 0


report = ValidationReport()


def test_static_data():
    """Test 1: Static Data Loading"""
    print("\n" + "=" * 70)
    print("TEST 1: Static Data Loading")
    print("=" * 70)

    try:
        # Load players
        all_players = players.get_players()
        if len(all_players) > 5000:
            report.add_pass(f"Load players (found {len(all_players)})")
        else:
            report.add_fail("Load players", f"Only found {len(all_players)} players")

        # Load teams
        all_teams = teams.get_teams()
        if len(all_teams) == 30:
            report.add_pass(f"Load teams (found {len(all_teams)})")
        else:
            report.add_fail("Load teams", f"Expected 30 teams, found {len(all_teams)}")

    except Exception as e:
        report.add_fail("Static data loading", str(e))


def test_entity_resolution():
    """Test 2: Entity Resolution (Uses Static Data)"""
    print("\n" + "=" * 70)
    print("TEST 2: Entity Resolution")
    print("=" * 70)

    test_cases = [
        ("LeBron James", "player", "LeBron James", 1.0),
        ("Lakers", "team", "Los Angeles Lakers", 1.0),
        ("Stephen Curry", "player", "Stephen Curry", 1.0),
        ("Warriors", "team", "Golden State Warriors", 1.0),
        ("Giannis", "player", "Giannis Antetokounmpo", 0.8),
        ("LAL", "team", "Los Angeles Lakers", 1.0),
        ("GSW", "team", "Golden State Warriors", 1.0),
    ]

    for query, entity_type, expected_name, min_confidence in test_cases:
        try:
            entity = resolve_entity(query, entity_type=entity_type)

            # Check name match
            name_match = expected_name.lower() in entity.name.lower()

            # Check confidence
            confidence_ok = entity.confidence >= min_confidence

            if name_match and confidence_ok:
                report.add_pass(
                    f"Resolve '{query}' → {entity.name} (conf: {entity.confidence:.2f})"
                )
            else:
                if not name_match:
                    report.add_fail(
                        f"Resolve '{query}'",
                        f"Expected '{expected_name}', got '{entity.name}'",
                    )
                if not confidence_ok:
                    report.add_fail(
                        f"Resolve '{query}'",
                        f"Confidence {entity.confidence:.2f} < {min_confidence}",
                    )

        except Exception as e:
            report.add_fail(f"Resolve '{query}'", str(e))


def test_entity_not_found():
    """Test 3: Entity Not Found Handling"""
    print("\n" + "=" * 70)
    print("TEST 3: Entity Not Found Handling")
    print("=" * 70)

    try:
        resolve_entity("XYZINVALIDPLAYER123", entity_type="player")
        report.add_fail("Entity not found", "Should have raised EntityNotFoundError")
    except EntityNotFoundError as e:
        # Verify error structure
        if e.code == "ENTITY_NOT_FOUND":
            report.add_pass("Entity not found raises correct error")
        else:
            report.add_fail("Entity not found", f"Wrong error code: {e.code}")

        # Check for suggestions
        if "suggestions" in e.details:
            report.add_pass("Entity not found includes suggestions")
        else:
            report.add_fail("Entity not found", "Missing suggestions in details")

    except Exception as e:
        report.add_fail("Entity not found", f"Wrong exception type: {type(e)}")


def test_response_envelope_structure():
    """Test 4: Response Envelope Structure"""
    print("\n" + "=" * 70)
    print("TEST 4: Response Envelope Structure")
    print("=" * 70)

    try:
        # Test success response
        resp = success_response(
            data={"test": "value"}, source="historical", execution_time_ms=100.5
        )

        # Check structure
        checks = [
            (resp.status == "success", "Status is 'success'"),
            (resp.data == {"test": "value"}, "Data is correct"),
            (resp.metadata.version == "v1", "Version is 'v1'"),
            (resp.metadata.schema_version == "2025-01", "Schema version is '2025-01'"),
            (resp.metadata.source == "historical", "Source is 'historical'"),
            (resp.errors is None or resp.errors == [], "Errors is None/empty"),
        ]

        for check, description in checks:
            if check:
                report.add_pass(f"Success response: {description}")
            else:
                report.add_fail(f"Success response: {description}", "Check failed")

        # Test error response
        err_resp = error_response("TEST_ERROR", "Test error message")

        err_checks = [
            (err_resp.status == "error", "Status is 'error'"),
            (err_resp.errors is not None, "Errors is not None"),
            (len(err_resp.errors) > 0, "Has error entries"),
            (err_resp.errors[0].code == "TEST_ERROR", "Error code is correct"),
        ]

        for check, description in err_checks:
            if check:
                report.add_pass(f"Error response: {description}")
            else:
                report.add_fail(f"Error response: {description}", "Check failed")

    except Exception as e:
        report.add_fail("Response envelope structure", str(e))


def test_response_json_serialization():
    """Test 5: Response JSON Serialization"""
    print("\n" + "=" * 70)
    print("TEST 5: Response JSON Serialization")
    print("=" * 70)

    try:
        resp = success_response(
            data={"player": "LeBron James", "ppg": 27.5}, source="historical"
        )

        # Serialize to JSON
        json_str = resp.to_json_string()

        # Parse back
        parsed = json.loads(json_str)

        # Verify structure
        checks = [
            ("status" in parsed, "Has 'status' field"),
            ("data" in parsed, "Has 'data' field"),
            ("metadata" in parsed, "Has 'metadata' field"),
            (parsed["status"] == "success", "Status is 'success'"),
            ("schema_version" in parsed["metadata"], "Has 'schema_version' in metadata"),
            (
                parsed["metadata"]["schema_version"] == "2025-01",
                "Schema version is '2025-01'",
            ),
        ]

        for check, description in checks:
            if check:
                report.add_pass(f"JSON serialization: {description}")
            else:
                report.add_fail(f"JSON serialization: {description}", "Check failed")

    except Exception as e:
        report.add_fail("JSON serialization", str(e))


def test_schema_versioning():
    """Test 6: Schema Versioning"""
    print("\n" + "=" * 70)
    print("TEST 6: Schema Versioning")
    print("=" * 70)

    try:
        # Create metadata
        metadata = ResponseMetadata()

        # Check fields
        checks = [
            (hasattr(metadata, "schema_version"), "Has 'schema_version' attribute"),
            (metadata.schema_version == "2025-01", "Default schema version is '2025-01'"),
            (len(metadata.schema_version) == 7, "Schema version has correct length"),
            (metadata.schema_version[4] == "-", "Schema version has correct format"),
        ]

        for check, description in checks:
            if check:
                report.add_pass(f"Schema versioning: {description}")
            else:
                report.add_fail(f"Schema versioning: {description}", "Check failed")

    except Exception as e:
        report.add_fail("Schema versioning", str(e))


def test_phase1_modules():
    """Test 7: Phase 1 Module Imports"""
    print("\n" + "=" * 70)
    print("TEST 7: Phase 1 Module Imports")
    print("=" * 70)

    modules_to_test = [
        ("nba_mcp.schemas.tool_params", "Tool parameter models"),
        ("nba_mcp.schemas.publisher", "Schema publisher"),
        ("nba_mcp.api.headers", "API headers module"),
        ("nba_mcp.api.schema_validator", "Schema validator"),
    ]

    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            report.add_pass(f"Import: {description} ({module_name})")
        except ImportError as e:
            report.add_fail(f"Import: {description}", str(e))


def test_schema_export():
    """Test 8: Schema Export Functionality"""
    print("\n" + "=" * 70)
    print("TEST 8: Schema Export Functionality")
    print("=" * 70)

    try:
        from nba_mcp.schemas.publisher import get_tool_schema, list_available_tools

        # Get list of tools
        tools = list_available_tools()

        if len(tools) >= 12:
            report.add_pass(f"List available tools (found {len(tools)})")
        else:
            report.add_fail("List available tools", f"Expected >= 12, found {len(tools)}")

        # Get a specific schema
        schema = get_tool_schema("resolve_nba_entity")

        schema_checks = [
            ("properties" in schema, "Schema has 'properties'"),
            ("title" in schema, "Schema has 'title'"),
            ("description" in schema, "Schema has 'description'"),
            (schema["title"] == "resolve_nba_entity", "Schema title is correct"),
        ]

        for check, description in schema_checks:
            if check:
                report.add_pass(f"Schema export: {description}")
            else:
                report.add_fail(f"Schema export: {description}", "Check failed")

    except Exception as e:
        report.add_fail("Schema export", str(e))


def test_headers_module():
    """Test 9: Headers Module Functionality"""
    print("\n" + "=" * 70)
    print("TEST 9: Headers Module Functionality")
    print("=" * 70)

    try:
        from nba_mcp.api.headers import (
            get_nba_headers,
            NBA_USER_AGENT,
            NBA_REFERER,
        )

        # Check constants
        checks = [
            ("NBA-MCP" in NBA_USER_AGENT, "User-Agent contains 'NBA-MCP'"),
            ("stats.nba.com" in NBA_REFERER, "Referer is 'stats.nba.com'"),
        ]

        for check, description in checks:
            if check:
                report.add_pass(f"Headers module: {description}")
            else:
                report.add_fail(f"Headers module: {description}", "Check failed")

        # Get headers
        headers = get_nba_headers()

        header_checks = [
            ("User-Agent" in headers, "Has 'User-Agent' header"),
            ("Referer" in headers, "Has 'Referer' header"),
            ("Accept" in headers, "Has 'Accept' header"),
            ("NBA-MCP" in headers["User-Agent"], "User-Agent contains 'NBA-MCP'"),
        ]

        for check, description in header_checks:
            if check:
                report.add_pass(f"Headers: {description}")
            else:
                report.add_fail(f"Headers: {description}", "Check failed")

    except Exception as e:
        report.add_fail("Headers module", str(e))


def main():
    """Run all offline validation tests."""
    print("=" * 70)
    print("NBA MCP OFFLINE VALIDATION")
    print("=" * 70)
    print("Testing functionality that doesn't require live NBA API calls")
    print()

    # Run all test suites
    test_static_data()
    test_entity_resolution()
    test_entity_not_found()
    test_response_envelope_structure()
    test_response_json_serialization()
    test_schema_versioning()
    test_phase1_modules()
    test_schema_export()
    test_headers_module()

    # Print summary
    report.print_summary()

    print("\n" + "=" * 70)
    print("NOTE: Live NBA API tests skipped due to rate limiting")
    print("This is expected behavior and validates our offline functionality")
    print("=" * 70)

    # Exit with appropriate code
    sys.exit(0 if report.tests_failed == 0 else 1)


if __name__ == "__main__":
    main()
