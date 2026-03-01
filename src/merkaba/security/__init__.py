# src/merkaba/security/__init__.py
"""Security module for Merkaba AI agent."""

from merkaba.security.permissions import PermissionManager, PermissionDenied
from merkaba.security.validation import validate_tool_arguments, ValidationError
from merkaba.security.secrets import store_secret, get_secret, delete_secret
from merkaba.security.integrity import (
    compute_file_hash,
    compute_directory_hashes,
    compare_with_baseline,
    save_baseline,
    load_baseline,
    IntegrityReport,
)
from merkaba.security.audit import scan_dependencies, CVEIssue
from merkaba.security.scanner import SecurityScanner, SecurityReport
from merkaba.security.classifier import InputClassifier

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
