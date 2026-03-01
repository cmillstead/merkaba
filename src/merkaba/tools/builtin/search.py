# src/friday/tools/builtin/search.py
import os
import re
from pathlib import Path
from friday.tools.base import Tool, PermissionTier


def _grep(pattern: str, path: str) -> str:
    """Search for regex pattern in file(s).

    Args:
        pattern: Regex pattern to search for
        path: File or directory path to search in

    Returns:
        Matching lines in format:
        - Single file: "line_num:line_content"
        - Multiple files/directory: "filepath:line_num:line_content"
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path does not exist: {path}")

    try:
        compiled_pattern = re.compile(pattern)
    except re.error as e:
        return f"[error] Invalid regex pattern: {e}"
    results = []

    if os.path.isfile(path):
        # Single file search
        matches = _search_file(path, compiled_pattern)
        for line_num, line_content in matches:
            results.append(f"{line_num}:{line_content}")
    else:
        # Directory search - recursive
        for root, _, files in os.walk(path):
            for filename in files:
                filepath = os.path.join(root, filename)
                matches = _search_file(filepath, compiled_pattern)
                for line_num, line_content in matches:
                    results.append(f"{filepath}:{line_num}:{line_content}")

    return "\n".join(results)


def _search_file(filepath: str, pattern: re.Pattern) -> list[tuple[int, str]]:
    """Search a single file for pattern matches.

    Args:
        filepath: Path to the file
        pattern: Compiled regex pattern

    Returns:
        List of (line_number, line_content) tuples for matching lines
    """
    matches = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                if pattern.search(line):
                    # Strip trailing newline but preserve other content
                    matches.append((line_num, line.rstrip("\n\r")))
    except UnicodeDecodeError:
        # Skip binary/non-UTF8 files
        pass
    except PermissionError:
        # Skip files we can't read
        pass
    return matches


grep = Tool(
    name="grep",
    description="Search for a regex pattern in file(s). Returns matching lines with line numbers.",
    function=_grep,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "The file or directory path to search in",
            },
        },
        "required": ["pattern", "path"],
    },
)


def _glob(pattern: str, path: str) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern to match (supports * and ** wildcards)
        path: Base directory path to search in

    Returns:
        Newline-separated list of matching file paths, or "No matches found"
    """
    base_path = Path(path)
    try:
        matches = list(base_path.glob(pattern))
    except (OSError, ValueError) as e:
        return f"[error] Glob failed: {e}"
    if not matches:
        return "No matches found"
    return "\n".join(str(m) for m in sorted(matches))


glob = Tool(
    name="glob",
    description="Find files matching a glob pattern. Supports * and ** wildcards.",
    function=_glob,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match (e.g., *.py, **/*.txt)",
            },
            "path": {
                "type": "string",
                "description": "The base directory path to search in",
            },
        },
        "required": ["pattern", "path"],
    },
)
