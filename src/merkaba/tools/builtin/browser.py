# src/merkaba/tools/builtin/browser.py
"""Browser automation tools with semantic snapshot parsing.

The semantic snapshot approach converts Playwright's accessibility tree
into structured text (~50KB) instead of screenshots (~5MB). This gives
the LLM structured, actionable information about interactive elements.
"""

import logging

logger = logging.getLogger(__name__)

# Roles to skip — presentational/structural with no semantic meaning
_SKIP_ROLES = frozenset({
    "generic",
    "none",
    "presentation",
    "group",
})

# Roles of interactive elements — highlighted in output
_INTERACTIVE_ROLES = frozenset({
    "button",
    "link",
    "textbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "menuitem",
    "tab",
    "switch",
    "slider",
    "spinbutton",
    "searchbox",
})


def format_a11y_tree(node: dict, indent: int = 0) -> str:
    """Format an accessibility tree node into structured text.

    Recursively walks the tree, skipping presentational roles,
    and producing indented text that an LLM can reason about.

    Args:
        node: Accessibility tree node (dict with role, name, children, etc.)
        indent: Current indentation level

    Returns:
        Formatted text representation of the tree.
    """
    lines: list[str] = []
    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")
    level = node.get("level")

    skip = role.lower() in _SKIP_ROLES and not name

    if not skip:
        prefix = "  " * indent
        parts: list[str] = []

        if role:
            role_str = role.lower()
            if level:
                role_str = f"{role_str} (level {level})"
            parts.append(f"[{role_str}]")

        if name:
            parts.append(f'"{name}"')

        if value:
            parts.append(f"value={value}")

        if parts:
            line = prefix + " ".join(parts)
            lines.append(line)
            indent += 1

    for child in node.get("children", []):
        child_text = format_a11y_tree(child, indent)
        if child_text:
            lines.append(child_text)

    return "\n".join(lines)
