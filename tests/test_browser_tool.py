# tests/test_browser_tool.py
"""Tests for browser tool semantic snapshot parser and Playwright tool wrappers.

All Playwright interactions are fully mocked — tests do NOT require Playwright
to be installed.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from merkaba.tools.base import PermissionTier
from merkaba.tools.builtin.browser import (
    format_a11y_tree,
    _validate_url,
    _run_async,
    browser_open,
    browser_snapshot,
    browser_click,
    browser_fill,
    browser_navigate,
    browser_close,
)


# -----------------------------------------------------------------------
# Accessibility tree formatter tests (no Playwright needed)
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# SSRF protection tests
# -----------------------------------------------------------------------


class TestSSRFProtection:
    """Verify that URL validation blocks internal/private addresses."""

    def test_blocks_localhost(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("http://localhost/secret")

    def test_blocks_private_ip(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("http://192.168.1.1/admin")

    def test_blocks_loopback(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("http://127.0.0.1/")

    def test_blocks_metadata_endpoint(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_metadata_hostname(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("http://metadata.google.internal/")

    def test_blocks_non_http_scheme(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("file:///etc/passwd")

    def test_allows_public_url(self):
        """Public URLs should pass validation (no exception)."""
        # Patch socket.gethostbyname to return a public IP
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            _validate_url("https://example.com")  # Should not raise


# -----------------------------------------------------------------------
# Tool definition tests
# -----------------------------------------------------------------------


class TestToolDefinitions:
    """Verify all browser tools have correct metadata."""

    def test_browser_open_definition(self):
        assert browser_open.name == "browser_open"
        assert browser_open.permission_tier == PermissionTier.SENSITIVE
        assert "url" in browser_open.parameters["properties"]
        assert "url" in browser_open.parameters["required"]

    def test_browser_snapshot_definition(self):
        assert browser_snapshot.name == "browser_snapshot"
        assert browser_snapshot.permission_tier == PermissionTier.MODERATE
        assert browser_snapshot.parameters["properties"] == {}

    def test_browser_click_definition(self):
        assert browser_click.name == "browser_click"
        assert browser_click.permission_tier == PermissionTier.SENSITIVE
        assert "selector" in browser_click.parameters["properties"]
        assert "selector" in browser_click.parameters["required"]

    def test_browser_fill_definition(self):
        assert browser_fill.name == "browser_fill"
        assert browser_fill.permission_tier == PermissionTier.SENSITIVE
        assert "selector" in browser_fill.parameters["properties"]
        assert "value" in browser_fill.parameters["properties"]
        assert "selector" in browser_fill.parameters["required"]
        assert "value" in browser_fill.parameters["required"]

    def test_browser_navigate_definition(self):
        assert browser_navigate.name == "browser_navigate"
        assert browser_navigate.permission_tier == PermissionTier.SENSITIVE
        assert "url" in browser_navigate.parameters["properties"]
        assert "url" in browser_navigate.parameters["required"]

    def test_browser_close_definition(self):
        assert browser_close.name == "browser_close"
        assert browser_close.permission_tier == PermissionTier.SAFE
        assert browser_close.parameters["properties"] == {}


# -----------------------------------------------------------------------
# Helpers: mock Playwright objects
# -----------------------------------------------------------------------


def _make_mock_page(
    url: str = "https://example.com",
    title: str = "Example",
    a11y_tree: dict | None = None,
):
    """Create a mock Playwright page with sensible defaults."""
    if a11y_tree is None:
        a11y_tree = {
            "role": "WebArea",
            "name": title,
            "children": [
                {"role": "heading", "name": "Hello", "level": 1},
                {"role": "button", "name": "Click"},
            ],
        }

    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.accessibility.snapshot = AsyncMock(return_value=a11y_tree)
    page.get_by_role = MagicMock(return_value=AsyncMock())
    page.get_by_label = MagicMock(return_value=AsyncMock())
    page.get_by_placeholder = MagicMock(return_value=AsyncMock())
    return page


def _make_mock_browser(page=None):
    """Create a mock Playwright browser."""
    browser = AsyncMock()
    if page is None:
        page = _make_mock_page()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    return browser


# -----------------------------------------------------------------------
# Tool execution tests (mocked Playwright)
# -----------------------------------------------------------------------


class TestBrowserOpen:
    """Tests for browser_open tool."""

    def test_open_returns_snapshot(self):
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            async def fake_ensure():
                return browser, page

            with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
                result = browser_open.execute(url="https://example.com")

        assert result.success is True
        assert "example.com" in result.output
        assert "Example" in result.output
        assert "button" in result.output
        assert "Hello" in result.output

    def test_open_ssrf_blocked(self):
        """Opening a private URL raises an error."""
        result = browser_open.execute(url="http://localhost/secret")
        assert result.success is False
        assert "not allowed" in result.error

    def test_open_private_ip_blocked(self):
        result = browser_open.execute(url="http://10.0.0.1/internal")
        assert result.success is False
        assert "not allowed" in result.error

    def test_open_no_a11y_tree(self):
        """Handle pages with no accessibility tree."""
        page = _make_mock_page()
        page.accessibility.snapshot = AsyncMock(return_value=None)
        browser = _make_mock_browser(page)

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            async def fake_ensure():
                return browser, page

            with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
                result = browser_open.execute(url="https://example.com")

        assert result.success is True
        assert "No accessibility tree" in result.output


class TestBrowserSnapshot:
    """Tests for browser_snapshot tool."""

    def test_snapshot_returns_tree(self):
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_snapshot.execute()

        assert result.success is True
        assert "Example" in result.output
        assert "button" in result.output
        assert "Hello" in result.output

    def test_snapshot_no_tree(self):
        page = _make_mock_page()
        page.accessibility.snapshot = AsyncMock(return_value=None)
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_snapshot.execute()

        assert result.success is True
        assert "No accessibility tree" in result.output


class TestBrowserClick:
    """Tests for browser_click tool."""

    def test_click_role_based(self):
        """Click using 'role:name' syntax."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)
        mock_locator = AsyncMock()
        page.get_by_role = MagicMock(return_value=mock_locator)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_click.execute(selector="button:Submit")

        assert result.success is True
        page.get_by_role.assert_called_once_with("button", name="Submit")
        mock_locator.click.assert_awaited_once()

    def test_click_css_selector(self):
        """Click using CSS selector."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_click.execute(selector="#login-btn")

        assert result.success is True
        page.click.assert_awaited_once_with("#login-btn", timeout=10000)

    def test_click_css_class_selector(self):
        """CSS class selectors should not be parsed as role:name."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_click.execute(selector=".btn:first-child")

        assert result.success is True
        # Should go through CSS path, not role-based
        page.click.assert_awaited_once_with(".btn:first-child", timeout=10000)


class TestBrowserFill:
    """Tests for browser_fill tool."""

    def test_fill_by_label(self):
        """Fill a field by its label text."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)
        mock_label_locator = AsyncMock()
        page.get_by_label = MagicMock(return_value=mock_label_locator)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_fill.execute(selector="Email", value="test@example.com")

        assert result.success is True
        page.get_by_label.assert_called_once_with("Email")
        mock_label_locator.fill.assert_awaited_once_with("test@example.com", timeout=5000)

    def test_fill_fallback_to_placeholder(self):
        """Fall back to placeholder if label lookup fails."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        # Label lookup raises, placeholder succeeds
        mock_label = AsyncMock()
        mock_label.fill = AsyncMock(side_effect=Exception("not found"))
        page.get_by_label = MagicMock(return_value=mock_label)

        mock_placeholder = AsyncMock()
        page.get_by_placeholder = MagicMock(return_value=mock_placeholder)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_fill.execute(selector="Enter your email", value="a@b.com")

        assert result.success is True
        page.get_by_placeholder.assert_called_once_with("Enter your email")
        mock_placeholder.fill.assert_awaited_once()

    def test_fill_fallback_to_css(self):
        """Fall back to CSS selector if label and placeholder fail."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        # Both label and placeholder fail
        mock_label = AsyncMock()
        mock_label.fill = AsyncMock(side_effect=Exception("not found"))
        page.get_by_label = MagicMock(return_value=mock_label)

        mock_placeholder = AsyncMock()
        mock_placeholder.fill = AsyncMock(side_effect=Exception("not found"))
        page.get_by_placeholder = MagicMock(return_value=mock_placeholder)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_fill.execute(selector="input#email", value="a@b.com")

        assert result.success is True
        page.fill.assert_awaited_once_with("input#email", "a@b.com", timeout=10000)


class TestBrowserNavigate:
    """Tests for browser_navigate tool."""

    def test_navigate_success(self):
        page = _make_mock_page(url="https://other.com", title="Other Site")
        browser = _make_mock_browser(page)

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            async def fake_ensure():
                return browser, page

            with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
                result = browser_navigate.execute(url="https://other.com")

        assert result.success is True
        assert "other.com" in result.output
        page.goto.assert_awaited_once()

    def test_navigate_ssrf_blocked(self):
        result = browser_navigate.execute(url="http://127.0.0.1:8080/admin")
        assert result.success is False
        assert "not allowed" in result.error

    def test_navigate_metadata_blocked(self):
        result = browser_navigate.execute(url="http://169.254.169.254/latest/")
        assert result.success is False
        assert "not allowed" in result.error


class TestBrowserClose:
    """Tests for browser_close tool."""

    def test_close_success(self):
        with patch("merkaba.tools.builtin.browser._close_browser", new_callable=lambda: AsyncMock) as mock_close:
            mock_close.return_value = None

            # Directly test the function
            import merkaba.tools.builtin.browser as bmod

            async def fake_close():
                bmod._browser = None
                bmod._page = None

            with patch("merkaba.tools.builtin.browser._close_browser", fake_close):
                result = browser_close.execute()

        assert result.success is True
        assert "closed" in result.output.lower()

    def test_close_when_no_browser(self):
        """Closing when no browser is open should still succeed."""
        import merkaba.tools.builtin.browser as bmod
        old_browser = bmod._browser
        old_page = bmod._page
        bmod._browser = None
        bmod._page = None

        try:
            async def fake_close():
                bmod._browser = None
                bmod._page = None

            with patch("merkaba.tools.builtin.browser._close_browser", fake_close):
                result = browser_close.execute()

            assert result.success is True
        finally:
            bmod._browser = old_browser
            bmod._page = old_page


# -----------------------------------------------------------------------
# Integration: __init__.py registration
# -----------------------------------------------------------------------


class TestRegistration:
    """Verify browser tools are importable from the builtin package."""

    def test_all_tools_in_module(self):
        from merkaba.tools.builtin import __all__ as all_names
        expected = [
            "browser_open",
            "browser_snapshot",
            "browser_click",
            "browser_fill",
            "browser_navigate",
            "browser_close",
        ]
        for name in expected:
            assert name in all_names, f"{name} missing from __all__"

    def test_tools_importable(self):
        from merkaba.tools.builtin import (
            browser_open as bo,
            browser_snapshot as bs,
            browser_click as bc,
            browser_fill as bf,
            browser_navigate as bn,
            browser_close as bcl,
        )
        # All should be Tool instances (not None) since browser.py
        # doesn't actually import playwright at module level
        assert bo is not None
        assert bs is not None
        assert bc is not None
        assert bf is not None
        assert bn is not None
        assert bcl is not None


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_open_file_scheme_blocked(self):
        """file:// URLs should be blocked."""
        result = browser_open.execute(url="file:///etc/passwd")
        assert result.success is False
        assert "not allowed" in result.error

    def test_open_ftp_scheme_blocked(self):
        """ftp:// URLs should be blocked."""
        result = browser_open.execute(url="ftp://evil.com/payload")
        assert result.success is False
        assert "not allowed" in result.error

    def test_navigate_no_scheme_blocked(self):
        """URLs without a scheme should be blocked."""
        result = browser_navigate.execute(url="example.com")
        assert result.success is False

    def test_click_role_with_noninteractive_role(self):
        """A 'role:name' where role isn't interactive falls through to CSS."""
        page = _make_mock_page()
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_click.execute(selector="heading:Welcome")

        assert result.success is True
        # "heading" is not in _INTERACTIVE_ROLES, so should fall through to CSS
        page.click.assert_awaited_once_with("heading:Welcome", timeout=10000)

    def test_snapshot_includes_page_url(self):
        """Snapshot output should include the current URL."""
        page = _make_mock_page(url="https://test.org/page")
        browser = _make_mock_browser(page)

        async def fake_ensure():
            return browser, page

        with patch("merkaba.tools.builtin.browser._ensure_browser", fake_ensure):
            result = browser_snapshot.execute()

        assert result.success is True
        assert "https://test.org/page" in result.output
