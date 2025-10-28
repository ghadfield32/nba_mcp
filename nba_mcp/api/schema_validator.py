"""
Schema drift detection for NBA API responses.
This module validates NBA API responses against expected schemas to detect
when the upstream API changes its data structure. This helps us:
"""

import json
import logging
import os
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Configuration

# Enable/disable schema validation via environment variable
ENABLE_SCHEMA_VALIDATION = (
    os.getenv("ENABLE_SCHEMA_VALIDATION", "false").lower() == "true"
)

# Validation mode: strict, warn, or log
SCHEMA_VALIDATION_MODE = os.getenv("SCHEMA_VALIDATION_MODE", "warn").lower()

# Directory containing expected schemas
EXPECTED_SCHEMAS_DIR = Path(__file__).parent / "expected_schemas"

# Validation Result Classes

@dataclass
class FieldMismatch:
    """Represents a field-level schema mismatch."""

    field_path: str  # e.g., "resultSets[0].rowSet"
    issue_type: str  # "missing_field", "type_mismatch", "unexpected_field"
    expected: Optional[str] = None  # Expected type/value
    actual: Optional[str] = None  # Actual type/value
    severity: str = "warning"  # "error", "warning", "info"

@dataclass
class ValidationResult:
    """Result of schema validation."""

    endpoint: str
    valid: bool
    mismatches: List[FieldMismatch] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    validated_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )

    def has_breaking_changes(self) -> bool:
        """Check if there are any breaking changes (missing required fields)."""
        return any(m.severity == "error" for m in self.mismatches)

    def has_warnings(self) -> bool:
        """Check if there are any warnings (non-breaking changes)."""
        return len(self.warnings) > 0 or any(
            m.severity == "warning" for m in self.mismatches
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "endpoint": self.endpoint,
            "valid": self.valid,
            "mismatches": [
                {
                    "field_path": m.field_path,
                    "issue_type": m.issue_type,
                    "expected": m.expected,
                    "actual": m.actual,
                    "severity": m.severity,
                }
                for m in self.mismatches
            ],
            "warnings": self.warnings,
            "errors": self.errors,
            "validated_at": self.validated_at,
        }

# Schema Validator

class SchemaValidator:
    """
    Validates NBA API responses against expected schemas.

    The validator loads expected schemas from JSON files and compares
    actual responses against them, detecting:
    - Missing required fields
    - Type mismatches
    - Unexpected new fields

    def __init__(self, schemas_dir: Optional[Path] = None):
        """
        Initialize the schema validator.

        Args:
            schemas_dir: Directory containing expected schema JSON files.
                        Defaults to nba_mcp/api/expected_schemas/
        """
        self.schemas_dir = schemas_dir or EXPECTED_SCHEMAS_DIR
        self.schemas_dir.mkdir(parents=True, exist_ok=True)
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._load_schemas()

    def _load_schemas(self):
        """Load all expected schemas from JSON files."""
        if not self.schemas_dir.exists():
            logger.warning(f"Expected schemas directory not found: {self.schemas_dir}")
            return

        for schema_file in self.schemas_dir.glob("*.json"):
            endpoint = schema_file.stem
            try:
                with open(schema_file, "r", encoding="utf-8") as f:
                    self.schemas[endpoint] = json.load(f)
                logger.debug(f"Loaded schema for endpoint: {endpoint}")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")

    def validate(self, endpoint: str, response: Dict[str, Any]) -> ValidationResult:
        """
        Validate a response against its expected schema.

        Args:
            endpoint: NBA API endpoint name (e.g., "playercareerstats")
            response: Actual response dictionary from NBA API

        Returns:
            ValidationResult with details of any mismatches

        result = ValidationResult(endpoint=endpoint, valid=True)

        # Check if we have an expected schema
        if endpoint not in self.schemas:
            result.warnings.append(
                f"No expected schema defined for endpoint: {endpoint}"
            )
            logger.debug(f"Skipping validation for {endpoint}: no schema defined")
            return result

        expected_schema = self.schemas[endpoint]

        # Validate required fields
        missing_fields = self._check_required_fields(expected_schema, response)
        if missing_fields:
            result.valid = False
            for field_path in missing_fields:
                result.mismatches.append(
                    FieldMismatch(
                        field_path=field_path,
                        issue_type="missing_field",
                        expected="present",
                        actual="missing",
                        severity="error",
                    )
                )
                result.errors.append(f"Missing required field: {field_path}")

        # Validate field types
        type_mismatches = self._check_field_types(expected_schema, response)
        for field_path, expected_type, actual_type in type_mismatches:
            result.mismatches.append(
                FieldMismatch(
                    field_path=field_path,
                    issue_type="type_mismatch",
                    expected=expected_type,
                    actual=actual_type,
                    severity="warning",
                )
            )
            result.warnings.append(
                f"Type mismatch at {field_path}: expected {expected_type}, got {actual_type}"
            )

        # Check for unexpected new fields
        new_fields = self._check_unexpected_fields(expected_schema, response)
        for field_path in new_fields:
            result.mismatches.append(
                FieldMismatch(
                    field_path=field_path,
                    issue_type="unexpected_field",
                    expected="not defined",
                    actual="present",
                    severity="info",
                )
            )
            result.warnings.append(f"New field detected: {field_path}")

        return result

    def _check_required_fields(
        self, expected: Dict[str, Any], actual: Dict[str, Any], prefix: str = ""
    ) -> List[str]:
        """
        Check for missing required fields.

        Args:
            expected: Expected schema with "required" field list
            actual: Actual response data
            prefix: Field path prefix for nested fields

        Returns:
            List of missing field paths
        """
        missing = []
        required_fields = expected.get("required", [])

        for field in required_fields:
            field_path = f"{prefix}.{field}" if prefix else field

            if field not in actual:
                missing.append(field_path)
            elif isinstance(expected.get("properties", {}).get(field), dict):
                # Recursively check nested objects
                nested_schema = expected["properties"][field]
                if "required" in nested_schema and isinstance(actual[field], dict):
                    missing.extend(
                        self._check_required_fields(
                            nested_schema, actual[field], field_path
                        )
                    )

        return missing

    def _check_field_types(
        self, expected: Dict[str, Any], actual: Dict[str, Any], prefix: str = ""
    ) -> List[Tuple[str, str, str]]:
        """
        Check for field type mismatches.

        Args:
            expected: Expected schema with "properties" field definitions
            actual: Actual response data
            prefix: Field path prefix for nested fields

        Returns:
            List of tuples: (field_path, expected_type, actual_type)
        """
        mismatches = []
        properties = expected.get("properties", {})

        for field, field_schema in properties.items():
            field_path = f"{prefix}.{field}" if prefix else field

            if field not in actual:
                continue  # Field is optional, handled by required check

            expected_type = field_schema.get("type")
            actual_value = actual[field]
            actual_type = type(actual_value).__name__

            # Map Python types to JSON Schema types
            type_map = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "list": "array",
                "dict": "object",
                "NoneType": "null",
            }
            actual_type_schema = type_map.get(actual_type, actual_type)

            if expected_type and expected_type != actual_type_schema:
                mismatches.append((field_path, expected_type, actual_type_schema))

            # Recursively check nested objects
            if isinstance(actual_value, dict) and "properties" in field_schema:
                mismatches.extend(
                    self._check_field_types(field_schema, actual_value, field_path)
                )

        return mismatches

    def _check_unexpected_fields(
        self, expected: Dict[str, Any], actual: Dict[str, Any], prefix: str = ""
    ) -> List[str]:
        """
        Check for unexpected new fields not in schema.

        Args:
            expected: Expected schema with "properties" field definitions
            actual: Actual response data
            prefix: Field path prefix for nested fields

        Returns:
            List of unexpected field paths
        """
        unexpected = []
        expected_fields = set(expected.get("properties", {}).keys())
        actual_fields = set(actual.keys())

        new_fields = actual_fields - expected_fields
        for field in new_fields:
            field_path = f"{prefix}.{field}" if prefix else field
            unexpected.append(field_path)

        return unexpected

# Global Validator Instance

_validator: Optional[SchemaValidator] = None

def get_validator() -> SchemaValidator:
    """
    Get the global schema validator instance (lazy initialization).

    Returns:
        SchemaValidator instance

    global _validator
    if _validator is None:
        _validator = SchemaValidator()
    return _validator

# Convenience Functions

def validate_response(endpoint: str, response: Dict[str, Any]) -> ValidationResult:
    """
    Validate an NBA API response (convenience function).

    This function checks if validation is enabled and the validation mode,
    then performs validation accordingly.

    Args:
        endpoint: NBA API endpoint name
        response: Actual response dictionary

    Returns:
        ValidationResult (or None if validation disabled)

    Raises:
        ValueError: If validation mode is "strict" and schema is invalid

    # Skip if validation is disabled
    if not ENABLE_SCHEMA_VALIDATION:
        return ValidationResult(endpoint=endpoint, valid=True)

    validator = get_validator()
    result = validator.validate(endpoint, response)

    # Handle validation result based on mode
    if SCHEMA_VALIDATION_MODE == "strict":
        if not result.valid:
            raise ValueError(
                f"Schema validation failed for {endpoint}: {result.errors}"
            )
    elif SCHEMA_VALIDATION_MODE == "warn":
        if result.has_breaking_changes():
            for error in result.errors:
                logger.error(f"[SCHEMA] {endpoint}: {error}")
        if result.has_warnings():
            for warning in result.warnings:
                logger.warning(f"[SCHEMA] {endpoint}: {warning}")
    elif SCHEMA_VALIDATION_MODE == "log":
        if result.has_breaking_changes() or result.has_warnings():
            logger.debug(f"[SCHEMA] {endpoint}: {result.to_dict()}")

    return result

def create_expected_schema(
    endpoint: str,
    response: Dict[str, Any],
    required_fields: List[str],
    output_dir: Optional[Path] = None,
):
    """
    Create an expected schema from a sample response (helper for setup).

    This function helps bootstrap schema definitions by analyzing a sample
    response and generating a basic schema JSON file.

    Args:
        endpoint: NBA API endpoint name
        response: Sample response to analyze
        required_fields: List of field names that are required
        output_dir: Directory to write schema file (default: expected_schemas/)

    output_dir = output_dir or EXPECTED_SCHEMAS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate schema from response structure
    def infer_type(value):
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            type(None): "null",
        }
        return type_map.get(type(value), "string")

    properties = {}
    for key, value in response.items():
        properties[key] = {"type": infer_type(value)}
        if isinstance(value, dict):
            properties[key]["properties"] = {
                k: {"type": infer_type(v)} for k, v in value.items()
            }

    schema = {
        "endpoint": endpoint,
        "description": f"Expected schema for NBA API endpoint: {endpoint}",
        "type": "object",
        "required": required_fields,
        "properties": properties,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Write to file
    schema_file = output_dir / f"{endpoint}.json"
    with open(schema_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, sort_keys=True)

    logger.info(f"Created expected schema: {schema_file}")

# Export

__all__ = [
    "SchemaValidator",
    "ValidationResult",
    "FieldMismatch",
    "validate_response",
    "get_validator",
    "create_expected_schema",
    "ENABLE_SCHEMA_VALIDATION",
    "SCHEMA_VALIDATION_MODE",
]
