# src/merkaba/plugins/sandbox.py
"""Plugin sandboxing — manifest-based tool and path restrictions."""

import os
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from merkaba.paths import merkaba_home as _merkaba_home


PROTECTED_PATHS = [
    "**/merkaba/security/*",
    "**/merkaba/approval/*",
    "**/.merkaba/config.json",
    "**/.merkaba/memory.db",
    "**/.merkaba/actions.db",
    "**/.merkaba/tasks.db",
    "**/.merkaba/conversations/*",
    "**/.merkaba/memory_vectors/*",
    "**/.merkaba/backups/*",
    "**/.merkaba/uploads/*",
    "**/.merkaba/logs/*",
]

# Resolved absolute paths for critical ~/.merkaba sub-directories.
# Used as a defense-in-depth layer alongside the fnmatch check — path
# traversal tricks that defeat fnmatch (e.g. symlinks, ``..`` segments)
# are still caught here because we compare fully-resolved strings.
_MERKABA_HOME = Path(_merkaba_home()).resolve()
_RESOLVED_PROTECTED_DIRS: list[str] = [
    str(_MERKABA_HOME / "conversations"),
    str(_MERKABA_HOME / "memory_vectors"),
    str(_MERKABA_HOME / "backups"),
    str(_MERKABA_HOME / "uploads"),
    str(_MERKABA_HOME / "logs"),
    # Individual protected files (stored as their parent + full path)
    str(_MERKABA_HOME / "config.json"),
    str(_MERKABA_HOME / "memory.db"),
    str(_MERKABA_HOME / "actions.db"),
    str(_MERKABA_HOME / "tasks.db"),
]

FILE_TOOLS = {"file_read", "file_write", "file_list"}


class PluginPermissionError(Exception):
    """Raised when a plugin tries to access a resource it hasn't declared."""


@dataclass
class PluginManifest:
    """Permission manifest declared in skill frontmatter."""

    name: str
    version: str = "0.1.0"
    required_tools: list[str] = field(default_factory=list)
    required_integrations: list[str] = field(default_factory=list)
    file_access: list[str] = field(default_factory=list)
    max_context_tokens: int = 4000
    permission_tier: str = "MODERATE"


@dataclass
class PluginSandbox:
    """Wraps tool execution with manifest-based restrictions."""

    manifest: PluginManifest
    allowed_business_ids: list[int] | None = None

    def check_business_access(self, business_id: int) -> None:
        """Raise PluginPermissionError if business_id is not in the allowed list.

        When ``allowed_business_ids`` is None, all businesses are accessible
        (backward-compatible default).
        """
        if self.allowed_business_ids is None:
            return
        if business_id not in self.allowed_business_ids:
            raise PluginPermissionError(
                f"Plugin '{self.manifest.name}' does not have access to business "
                f"id {business_id!r}. Allowed business ids: {self.allowed_business_ids}"
            )

    def check_tool_access(self, tool_name: str) -> None:
        """Raise PluginPermissionError if tool not declared in manifest."""
        if tool_name not in self.manifest.required_tools:
            raise PluginPermissionError(
                f"Plugin '{self.manifest.name}' does not have access to tool '{tool_name}'. "
                f"Declared tools: {self.manifest.required_tools}"
            )

    def check_path_access(self, tool_name: str, args: dict) -> None:
        """Check path arguments against manifest allowlist and PROTECTED_PATHS."""
        if tool_name not in FILE_TOOLS:
            return
        path = args.get("path", "")
        if not path:
            return
        if not self.is_path_allowed(path):
            raise PluginPermissionError(
                f"Plugin '{self.manifest.name}' cannot access path '{path}'. "
                f"Allowed patterns: {self.manifest.file_access}"
            )

    def is_path_allowed(self, path: str) -> bool:
        """Return True if path passes both protected check and manifest allowlist.

        Protection is applied in two complementary layers:

        1. **fnmatch check** against ``PROTECTED_PATHS`` glob patterns — fast
           and covers the common cases.
        2. **Resolved-path check** against ``_RESOLVED_PROTECTED_DIRS`` — a
           defense-in-depth layer that catches path-traversal attempts (e.g.
           ``../../.merkaba/config.json``) that might slip past fnmatch because
           the pattern never sees the canonical absolute path.
        """
        resolved = str(Path(os.path.expanduser(path)).resolve())

        # --- Layer 1: fnmatch against glob patterns ---
        for pattern in PROTECTED_PATHS:
            expanded = str(Path(os.path.expanduser(pattern)))
            if fnmatch(resolved, expanded):
                return False

        # --- Layer 2: resolved-path prefix / exact match ---
        for protected in _RESOLVED_PROTECTED_DIRS:
            # Directory entries: block anything inside the directory
            if protected.endswith(("/conversations", "/memory_vectors", "/backups", "/uploads", "/logs")):
                if resolved.startswith(protected + os.sep) or resolved == protected:
                    return False
            else:
                # Exact file match
                if resolved == protected:
                    return False

        # Check manifest allowlist
        if not self.manifest.file_access:
            return False

        for pattern in self.manifest.file_access:
            expanded = str(Path(os.path.expanduser(pattern)).resolve()) if not pattern.startswith("*") else pattern
            if fnmatch(resolved, expanded):
                return True

        return False
