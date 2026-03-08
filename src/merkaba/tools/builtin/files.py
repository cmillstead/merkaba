# src/merkaba/tools/builtin/files.py
import os
import re
from pathlib import Path
from merkaba.tools.base import Tool, PermissionTier
from merkaba.paths import config_path as _config_path


# Denied directory paths (will block any path under these)
DENIED_PATHS = [
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "~/.config/gcloud",
    "~/.kube",
    "~/.azure",
    "~/.netrc",
    "~/.git-credentials",
    _config_path(),
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
]

# Denied filename patterns (will block files matching these names anywhere)
DENIED_FILENAME_PATTERNS = [
    r"^\.env$",
    r"^\.env\.local$",
    r"^\.env\.production$",
    r"^credentials\.json$",
    r"^secrets\.yaml$",
    r"^id_rsa$",
    r"^id_ed25519$",
]

# Shell config files blocked for write operations only
SHELL_CONFIG_FILES = [
    "~/.bashrc",
    "~/.zshrc",
    "~/.profile",
    "~/.bash_profile",
    "~/.zprofile",
]


def _expand_path(path: str) -> Path:
    """Expand ~ and resolve the path to absolute form."""
    return Path(os.path.expanduser(path)).resolve()


def _normalize_path(path: str) -> Path:
    """Normalize a path, expanding ~ and resolving to absolute path."""
    expanded = os.path.expanduser(path)
    return Path(expanded).resolve()


def is_path_allowed(path: str, for_write: bool = False) -> tuple[bool, str]:
    """
    Check if a file path is allowed for read/write operations.

    Args:
        path: The file path to check
        for_write: If True, also check shell config restrictions

    Returns:
        Tuple of (is_allowed, reason). If not allowed, reason explains why.
    """
    try:
        normalized = _normalize_path(path)
    except Exception as e:
        return False, f"Invalid path: {e}"

    # Check against denied directory paths
    for denied in DENIED_PATHS:
        denied_expanded = _expand_path(denied)
        # Check if the path is the denied path or under it
        try:
            normalized.relative_to(denied_expanded)
            return False, f"Access denied: path '{path}' is within restricted directory '{denied}'"
        except ValueError:
            # Not a subpath, check if it's the exact path
            if normalized == denied_expanded:
                return False, f"Access denied: path '{path}' matches restricted path '{denied}'"

    # Check filename against denied patterns
    filename = normalized.name
    for pattern in DENIED_FILENAME_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return False, f"Access denied: filename '{filename}' matches restricted pattern"

    # For write operations, also check shell config files
    if for_write:
        for shell_config in SHELL_CONFIG_FILES:
            config_expanded = _expand_path(shell_config)
            if normalized == config_expanded:
                return False, f"Access denied: cannot write to shell config file '{shell_config}'"

    return True, "Path is allowed"


def _file_read(path: str) -> str:
    """Read contents of a file."""
    # Check path restrictions
    allowed, reason = is_path_allowed(path, for_write=False)
    if not allowed:
        raise PermissionError(reason)

    try:
        with open(path, "r") as f:
            return f.read()
    except UnicodeDecodeError:
        return f"[error] Cannot read '{path}': file appears to be binary"


def _file_write(path: str, content: str) -> str:
    """Write content to a file."""
    # Check path restrictions (including shell config files)
    allowed, reason = is_path_allowed(path, for_write=True)
    if not allowed:
        raise PermissionError(reason)

    # Ensure directory exists
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} characters to {path}"


def _file_list(path: str) -> str:
    """List contents of a directory."""
    allowed, reason = is_path_allowed(path, for_write=False)
    if not allowed:
        return f"[error] Access denied: {reason}"
    try:
        entries = os.listdir(path)
    except OSError as e:
        return f"[error] Cannot list '{path}': {e}"
    result = []
    for entry in sorted(entries):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            result.append(f"[DIR]  {entry}")
        else:
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            result.append(f"[FILE] {entry} ({size} bytes)")
    return "\n".join(result)


file_read = Tool(
    name="file_read",
    description="Read the contents of a file at the given path",
    function=_file_read,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the file to read",
            }
        },
        "required": ["path"],
    },
)

file_write = Tool(
    name="file_write",
    description="Write content to a file at the given path",
    function=_file_write,
    permission_tier=PermissionTier.MODERATE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to write the file to",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
)

file_list = Tool(
    name="file_list",
    description="List contents of a directory",
    function=_file_list,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The directory path to list",
            }
        },
        "required": ["path"],
    },
)
