# src/friday/plugins/sandbox.py
"""Plugin sandboxing — manifest-based tool and path restrictions."""

import os
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path


PROTECTED_PATHS = [
    "**/friday/security/*",
    "**/friday/approval/*",
    "**/.friday/config.json",
    "**/.friday/memory.db",
    "**/.friday/actions.db",
    "**/.friday/tasks.db",
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
        """Return True if path passes both protected check and manifest allowlist."""
        resolved = str(Path(os.path.expanduser(path)).resolve())

        # Block protected paths regardless of manifest
        for pattern in PROTECTED_PATHS:
            expanded = str(Path(os.path.expanduser(pattern)))
            if fnmatch(resolved, expanded):
                return False

        # Check manifest allowlist
        if not self.manifest.file_access:
            return False

        for pattern in self.manifest.file_access:
            expanded = str(Path(os.path.expanduser(pattern)).resolve()) if not pattern.startswith("*") else pattern
            if fnmatch(resolved, expanded):
                return True

        return False
