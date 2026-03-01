# src/friday/security/__init__.py
"""Security module for Friday AI agent."""

from friday.security.permissions import PermissionManager, PermissionDenied
from friday.security.validation import validate_tool_arguments, ValidationError
from friday.security.secrets import store_secret, get_secret, delete_secret
from friday.security.integrity import (
    compute_file_hash,
    compute_directory_hashes,
    compare_with_baseline,
    save_baseline,
    load_baseline,
    IntegrityReport,
)
from friday.security.audit import scan_dependencies, CVEIssue
from friday.security.scanner import SecurityScanner, SecurityReport
from friday.security.classifier import InputClassifier

__all__ = [
    "PermissionManager",
    "PermissionDenied",
    "validate_tool_arguments",
    "ValidationError",
    "store_secret",
    "get_secret",
    "delete_secret",
    "compute_file_hash",
    "compute_directory_hashes",
    "compare_with_baseline",
    "save_baseline",
    "load_baseline",
    "IntegrityReport",
    "scan_dependencies",
    "CVEIssue",
    "SecurityScanner",
    "SecurityReport",
    "InputClassifier",
]
