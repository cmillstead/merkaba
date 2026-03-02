# tests/test_browser_tool.py
"""Tests for browser tool semantic snapshot parser."""

from merkaba.tools.builtin.browser import format_a11y_tree


def test_format_simple_page():
    """Format a simple page with heading and text."""
    tree = {
        "role": "WebArea",
        "name": "Test Page",
        "children": [
            {"role": "heading", "name": "Welcome", "level": 1},
            {"role": "text", "name": "Hello World"},
        ],
    }
    result = format_a11y_tree(tree)
    assert "heading" in result
    assert "Welcome" in result
    assert "Hello World" in result


def test_format_interactive_elements():
    """Format form elements with roles and values."""
    tree = {
        "role": "WebArea",
        "name": "Form Page",
        "children": [
            {"role": "textbox", "name": "Email", "value": "user@test.com"},
            {"role": "button", "name": "Submit"},
            {
                "role": "link",
                "name": "Forgot password",
                "url": "https://example.com/reset",
            },
        ],
    }
    result = format_a11y_tree(tree)
    assert "textbox" in result
    assert "Email" in result
    assert "user@test.com" in result
    assert "button" in result
    assert "Submit" in result
    assert "link" in result


def test_format_nested_structure():
    """Format nested elements with proper indentation."""
    tree = {
        "role": "WebArea",
        "name": "Page",
        "children": [
            {
                "role": "navigation",
                "name": "Main nav",
                "children": [
                    {"role": "link", "name": "Home"},
                    {"role": "link", "name": "About"},
                ],
            },
            {
                "role": "main",
                "children": [
                    {"role": "heading", "name": "Content", "level": 2},
                ],
            },
        ],
    }
    result = format_a11y_tree(tree)
    # Check indentation exists (nested items should be indented)
    lines = result.strip().split("\n")
    indented = [line for line in lines if line.startswith("  ")]
    assert len(indented) > 0


def test_format_empty_tree():
    """Empty tree returns minimal output."""
    tree = {"role": "WebArea", "name": "Empty"}
    result = format_a11y_tree(tree)
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_skips_presentational_roles():
    """Presentational/generic roles are skipped to reduce noise."""
    tree = {
        "role": "WebArea",
        "name": "Page",
        "children": [
            {
                "role": "generic",
                "children": [
                    {
                        "role": "generic",
                        "children": [{"role": "button", "name": "Click me"}],
                    }
                ],
            },
        ],
    }
    result = format_a11y_tree(tree)
    assert "button" in result
    assert "Click me" in result
    # "generic" role should not appear (skipped)
    assert "generic" not in result.lower()
