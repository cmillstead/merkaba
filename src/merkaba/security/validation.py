# src/friday/security/validation.py
"""Input validation for tool arguments to prevent prompt injection and type mismatches."""

import re
import unicodedata
from typing import Any


class ValidationError(Exception):
    """Raised when tool argument validation fails."""

    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        self.message = message
        super().__init__(f"Validation failed for {tool_name}: {message}")


# Patterns that indicate potential prompt injection attempts
INJECTION_PATTERNS = [
    # Direct instruction override attempts
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard.*instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"new\s+persona", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    # Special tokens used by various LLMs
    re.compile(r"<\|.*?\|>"),  # OpenAI/GPT special tokens
    re.compile(r"\[INST\]", re.IGNORECASE),  # Llama instruction tokens
    re.compile(r"\[/INST\]", re.IGNORECASE),  # Llama instruction tokens
]


# Common Cyrillic/Greek homoglyphs that look like Latin letters
CONFUSABLES = {
    "\u0430": "a",  # Cyrillic а
    "\u0435": "e",  # Cyrillic е
    "\u043e": "o",  # Cyrillic о
    "\u0440": "p",  # Cyrillic р
    "\u0441": "c",  # Cyrillic с
    "\u0443": "y",  # Cyrillic у
    "\u0445": "x",  # Cyrillic х
    "\u0456": "i",  # Cyrillic і
    "\u0391": "A",  # Greek Α
    "\u0392": "B",  # Greek Β
    "\u0395": "E",  # Greek Ε
    "\u0397": "H",  # Greek Η
    "\u0399": "I",  # Greek Ι
    "\u039a": "K",  # Greek Κ
    "\u039c": "M",  # Greek Μ
    "\u039d": "N",  # Greek Ν
    "\u039f": "O",  # Greek Ο
    "\u03a1": "P",  # Greek Ρ
    "\u03a4": "T",  # Greek Τ
    "\u03a7": "X",  # Greek Χ
    "\u03a5": "Y",  # Greek Υ
    "\u0417": "Z",  # Cyrillic З
}


def _normalize_unicode(text: str) -> str:
    """Normalize unicode to catch homoglyph attacks.

    Two-stage normalization:
    1. Replace known confusable characters (Cyrillic/Greek lookalikes)
    2. Apply NFKC normalization for full-width and other variants

    This catches attacks like:
    - Cyrillic 'і' (U+0456) -> Latin 'i'
    - Full-width 'ｉｇｎｏｒｅ' -> 'ignore'
    """
    # First pass: replace known confusables
    for confusable, replacement in CONFUSABLES.items():
        text = text.replace(confusable, replacement)

    # Second pass: NFKC normalization for full-width, etc.
    return unicodedata.normalize("NFKC", text)


def _check_string_injection(value: str) -> tuple[bool, str | None]:
    """Check if a string contains prompt injection patterns.

    Args:
        value: The string value to check

    Returns:
        Tuple of (is_safe, detected_pattern) where is_safe is True if no
        injection patterns found, False otherwise. detected_pattern contains
        the matched pattern if found.
    """
    # Normalize unicode to catch homoglyph attacks
    normalized = _normalize_unicode(value)

    for pattern in INJECTION_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return False, match.group()

    return True, None


def _check_prompt_injection_recursive(
    value: Any, path: str
) -> tuple[bool, str | None, str]:
    """Recursively check if a value contains prompt injection patterns.

    Handles strings, lists, and dicts with arbitrary nesting depth.

    Args:
        value: The value to check (string, list, dict, or other)
        path: The current path for error reporting (e.g., "items[0].description")

    Returns:
        Tuple of (is_safe, detected_pattern, location_path) where is_safe is True if no
        injection patterns found. detected_pattern and location_path contain details
        if injection is found.
    """
    if value is None:
        return True, None, path

    if isinstance(value, str):
        is_safe, pattern = _check_string_injection(value)
        return is_safe, pattern, path

    if isinstance(value, list):
        for i, item in enumerate(value):
            is_safe, pattern, item_path = _check_prompt_injection_recursive(
                item, f"{path}[{i}]"
            )
            if not is_safe:
                return False, pattern, item_path

    if isinstance(value, dict):
        for key, val in value.items():
            is_safe, pattern, val_path = _check_prompt_injection_recursive(
                val, f"{path}.{key}"
            )
            if not is_safe:
                return False, pattern, val_path

    return True, None, path


def _check_type(value: Any, expected_type: str) -> tuple[bool, str]:
    """Check if a value matches the expected JSON schema type.

    Args:
        value: The value to check
        expected_type: The JSON schema type (string, integer, boolean, number, array, object)

    Returns:
        Tuple of (matches, error_message)
    """
    type_map = {
        "string": str,
        "integer": int,
        "boolean": bool,
        "number": (int, float),
        "array": list,
        "object": dict,
    }

    if expected_type not in type_map:
        # Unknown type, allow it
        return True, ""

    expected_python_type = type_map[expected_type]

    # Special case: boolean should not match int (since bool is subclass of int)
    if expected_type == "boolean":
        if not isinstance(value, bool):
            return False, f"expected boolean, got {type(value).__name__}"
        return True, ""

    # Special case: integer should not match boolean
    if expected_type == "integer":
        if isinstance(value, bool):
            return False, f"expected integer, got boolean"
        if not isinstance(value, int):
            return False, f"expected integer, got {type(value).__name__}"
        return True, ""

    # Special case: number should accept int or float but not bool
    if expected_type == "number":
        if isinstance(value, bool):
            return False, f"expected number, got boolean"
        if not isinstance(value, (int, float)):
            return False, f"expected number, got {type(value).__name__}"
        return True, ""

    if not isinstance(value, expected_python_type):
        return False, f"expected {expected_type}, got {type(value).__name__}"

    return True, ""


def validate_tool_arguments(
    tool_name: str,
    parameters_schema: dict,
    arguments: dict,
) -> tuple[bool, str]:
    """Validate tool arguments against schema and check for prompt injection.

    Args:
        tool_name: Name of the tool being called
        parameters_schema: JSON schema for the tool's parameters
        arguments: The arguments provided to the tool

    Returns:
        Tuple of (is_valid, error_message). If is_valid is True, error_message
        will be empty. If False, error_message describes the validation failure.
    """
    if not isinstance(arguments, dict):
        return False, "arguments must be a dictionary"

    properties = parameters_schema.get("properties", {})
    required = parameters_schema.get("required", [])

    # Check for unknown arguments
    for arg_name in arguments:
        if arg_name not in properties:
            return False, f"unknown argument: {arg_name}"

    # Check required fields are present
    for field_name in required:
        if field_name not in arguments:
            return False, f"missing required field: {field_name}"

    # Validate each argument
    for arg_name, arg_value in arguments.items():
        prop_schema = properties.get(arg_name, {})

        # Check type if specified
        if "type" in prop_schema:
            type_valid, type_error = _check_type(arg_value, prop_schema["type"])
            if not type_valid:
                return False, f"field '{arg_name}': {type_error}"

        # Recursively check for prompt injection in all values
        is_safe, pattern, location = _check_prompt_injection_recursive(
            arg_value, arg_name
        )
        if not is_safe:
            return False, f"potential prompt injection detected in '{location}': '{pattern}'"

    return True, ""
