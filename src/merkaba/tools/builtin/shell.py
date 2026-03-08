# src/merkaba/tools/builtin/shell.py
"""Secure shell command execution with allowlist-based filtering."""
import os
import re
import shlex
import subprocess
from merkaba.tools.base import Tool, PermissionTier

# Allowlist of commands that can be executed.
# NOTE: "env" was intentionally removed — it is a generic program launcher
# (e.g. "env python3 -c ...") that would defeat the entire allowlist (H3).
ALLOWED_COMMANDS = {
    "git", "pytest", "uv", "pip", "npm",
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "mkdir", "cp", "mv", "echo", "pwd", "whoami", "date", "which",
}

# Commands that require subcommand validation
SUBCOMMAND_ALLOWLISTS = {
    "git": {"status", "diff", "log", "add", "commit", "push", "pull", "branch", "checkout", "stash"},
    "pip": {"install", "list", "show"},
    "npm": {"install", "test", "run", "list"},
}

# find flags that would allow arbitrary command execution or mass deletion (H2).
# "-exec"/"-execdir" run an arbitrary command per match, bypassing pipe detection.
# "-ok"/"-okdir" are interactive variants of -exec.
# "-delete" can silently wipe large trees.
_FIND_DANGEROUS_FLAGS = {"-exec", "-execdir", "-ok", "-okdir", "-delete"}

# Paths that cp/mv must never read from or write to (H2).
# Expanduser is called at module load time so the check is path-based, not
# pattern-based, and is immune to tilde-expansion tricks.
from merkaba.paths import merkaba_home as _merkaba_home

_FORBIDDEN_CP_MV_PATHS = [
    _merkaba_home(),
    os.path.expanduser("~/.ssh"),
    os.path.expanduser("~/.aws"),
    os.path.expanduser("~/.gnupg"),
]

# Patterns that indicate access to sensitive files/locations
FORBIDDEN_PATTERNS = [
    r"/etc/passwd",
    r"/etc/shadow",
    r"~/.ssh",
    r"\$HOME/.ssh",
    r"\${HOME}/.ssh",
    r"/home/[^/]+/.ssh",
    r"~/.gnupg",
    r"\$HOME/.gnupg",
    r"~/.aws",
    r"\$HOME/.aws",
    r"\.env\b",  # .env files (word boundary to avoid matching .environment)
    r"config\.json\b",
]

# Timeout for command execution in seconds
COMMAND_TIMEOUT_SECONDS = 60

# Patterns that indicate shell injection or dangerous constructs
DANGEROUS_PATTERNS = [
    r"`[^`]+`",  # Backtick command substitution
    r"\$\([^)]+\)",  # $() command substitution
    r";\s*",  # Command chaining with semicolon (commented out for now - might be too strict)
    r"\|\s*",  # Piping (we'll check the full command for sensitive patterns)
    r">\s*~",  # Redirect to home directory paths
]


def _normalize_path(path: str) -> str:
    """Normalize a path for pattern matching."""
    # Replace multiple slashes with single slash
    normalized = re.sub(r"/+", "/", path)
    return normalized


def _contains_forbidden_pattern(command: str) -> tuple[bool, str]:
    """Check if command contains any forbidden patterns indicating sensitive file access."""
    # Normalize the command for better pattern matching
    normalized = _normalize_path(command)

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return True, f"Command contains forbidden pattern accessing sensitive files: {pattern}"

    return False, ""


def _contains_dangerous_construct(command: str) -> tuple[bool, str]:
    """Check for shell injection or dangerous shell constructs."""
    # Check for backtick substitution
    if "`" in command:
        return True, "Command contains backtick command substitution which is not allowed"

    # Check for $() substitution
    if re.search(r"\$\([^)]+\)", command):
        return True, "Command contains $() command substitution which is not allowed"

    # Check for redirects to sensitive locations
    if re.search(r">\s*~", command) or re.search(r">\s*\$HOME", command):
        return True, "Command contains redirect to sensitive location"

    # Check for piping (command chaining via pipe)
    # Match | that is not part of || (logical OR) and not part of redirects like 2>&1
    if re.search(r"(?<![|>&])\|(?![|])", command):
        return True, "Command contains pipe which is not allowed"

    return False, ""


def _extract_base_command(command: str) -> tuple[str, list[str]]:
    """Extract the base command and arguments using shlex.split().

    Returns:
        Tuple of (base_command, arguments) where base_command is the executable name
        (basename if it's a path) and arguments is the list of remaining tokens.
    """
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        # If shlex fails to parse, return empty
        return "", []

    if not tokens:
        return "", []

    base_cmd = tokens[0]
    args = tokens[1:] if len(tokens) > 1 else []

    # Extract basename if it's a path (e.g., /usr/bin/python -> python)
    if "/" in base_cmd:
        base_cmd = os.path.basename(base_cmd)

    return base_cmd, args


def is_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is allowed based on the allowlist.

    Args:
        command: The shell command to validate.

    Returns:
        Tuple of (allowed, reason) where allowed is True if the command is permitted,
        and reason explains why if not allowed.
    """
    # Check for empty or whitespace-only commands
    if not command or not command.strip():
        return False, "Empty command is not allowed"

    # Check for dangerous shell constructs first
    is_dangerous, danger_reason = _contains_dangerous_construct(command)
    if is_dangerous:
        return False, danger_reason

    # Check for forbidden patterns (sensitive file access)
    has_forbidden, forbidden_reason = _contains_forbidden_pattern(command)
    if has_forbidden:
        return False, forbidden_reason

    # Extract the base command
    base_cmd, args = _extract_base_command(command)

    if not base_cmd:
        return False, "Could not parse command"

    # Check if base command is in allowlist
    if base_cmd not in ALLOWED_COMMANDS:
        return False, f"Command '{base_cmd}' is not in allowlist"

    # Check subcommand restrictions for specific commands
    if base_cmd in SUBCOMMAND_ALLOWLISTS:
        allowed_subcommands = SUBCOMMAND_ALLOWLISTS[base_cmd]

        if not args:
            # Some commands need a subcommand (pip, npm)
            if base_cmd in ("pip", "npm"):
                return False, f"Command '{base_cmd}' requires a subcommand"
            # git without args is OK (e.g., just 'git' shows help)
            return True, ""

        subcommand = args[0]

        # Skip flag arguments (they start with -)
        if subcommand.startswith("-"):
            # Find the actual subcommand
            for arg in args:
                if not arg.startswith("-"):
                    subcommand = arg
                    break
            else:
                # Only flags, no subcommand - might be OK for some commands
                if base_cmd == "git":
                    return True, ""
                return False, f"Command '{base_cmd}' requires a valid subcommand"

        if subcommand not in allowed_subcommands:
            return False, f"Subcommand '{subcommand}' is not allowed for '{base_cmd}'. Allowed: {', '.join(sorted(allowed_subcommands))}"

    # Block dangerous find flags that allow arbitrary command execution or mass deletion (H2).
    if base_cmd == "find":
        for arg in args:
            if arg in _FIND_DANGEROUS_FLAGS:
                return False, (
                    f"find flag '{arg}' is not allowed — it enables arbitrary command "
                    f"execution or mass deletion. Dangerous flags: "
                    f"{', '.join(sorted(_FIND_DANGEROUS_FLAGS))}"
                )

    # Restrict cp/mv to prevent exfiltration of or tampering with sensitive data (H2).
    if base_cmd in ("cp", "mv"):
        for arg in args:
            # Skip flags (e.g. -r, -f, --recursive)
            if arg.startswith("-"):
                continue
            expanded = os.path.expanduser(arg)
            # Resolve to absolute so that relative paths containing ~/ tokens are
            # caught even if the tilde was not in the leading position.
            for forbidden in _FORBIDDEN_CP_MV_PATHS:
                if expanded == forbidden or expanded.startswith(forbidden + os.sep):
                    return False, (
                        f"Path '{arg}' is under a restricted directory "
                        f"({forbidden}) and cannot be used with cp/mv"
                    )

    return True, ""


# Keep is_blocked for backwards compatibility but it now uses is_allowed internally
def is_blocked(command: str) -> bool:
    """Check if a command is blocked (inverse of is_allowed for backwards compatibility)."""
    allowed, _ = is_allowed(command)
    return not allowed


def _bash(command: str) -> str:
    """Execute a shell command.

    Uses ``shell=False`` with ``shlex.split()`` to avoid shell-injection risks.
    The allowlist in ``is_allowed()`` already rejects pipes, redirects, and
    command-substitution constructs, so every command that reaches this point
    is a plain executable + arguments that can be safely split and exec'd
    directly without invoking a shell interpreter.
    """
    allowed, reason = is_allowed(command)
    if not allowed:
        raise PermissionError(f"Command not allowed: {reason}")

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return f"[error] Could not parse command: {exc}"

    try:
        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"[error] Command timed out after {COMMAND_TIMEOUT_SECONDS} seconds"

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"

    return output.strip() if output else "(no output)"


bash = Tool(
    name="bash",
    description="Execute a shell command. Only allowlisted commands are permitted for safety.",
    function=_bash,
    permission_tier=PermissionTier.SENSITIVE,
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"}
        },
        "required": ["command"],
    },
)
