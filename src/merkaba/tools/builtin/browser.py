# src/merkaba/tools/builtin/browser.py
"""Browser automation tools with semantic snapshot parsing.

The semantic snapshot approach converts Playwright's accessibility tree
into structured text (~50KB) instead of screenshots (~5MB). This gives
the LLM structured, actionable information about interactive elements.

Requires: pip install merkaba[browser]  (installs playwright)
After install: python -m playwright install chromium
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from merkaba.tools.base import Tool, PermissionTier

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


# ---------------------------------------------------------------------------
# Sync wrapper for async Playwright operations
# ---------------------------------------------------------------------------

# Dedicated event loop running on a background thread for Playwright.
# Playwright's async API requires an event loop; the agent loop is sync,
# so we run Playwright in a persistent background loop to avoid
# creating/destroying loops (which breaks Playwright's internal state).
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Return (and lazily create) the background event loop for Playwright."""
    global _loop
    if _loop is not None and _loop.is_running():
        return _loop
    with _loop_lock:
        if _loop is not None and _loop.is_running():
            return _loop
        _loop = asyncio.new_event_loop()

        def _run(loop: asyncio.AbstractEventLoop) -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        t = threading.Thread(target=_run, args=(_loop,), daemon=True)
        t.start()
        return _loop


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on the background Playwright event loop.

    Blocks the calling (sync) thread until the coroutine finishes.
    """
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=60)


# ---------------------------------------------------------------------------
# SSRF protection — reuse validation from web.py
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    """Validate a URL against SSRF rules.  Raises ValueError if blocked."""
    from merkaba.tools.builtin.web import is_url_allowed

    allowed, reason = is_url_allowed(url)
    if not allowed:
        raise ValueError(f"URL not allowed: {reason}")


# ---------------------------------------------------------------------------
# Browser session management
# ---------------------------------------------------------------------------

# Singleton browser + page managed across tool calls.
# The agent opens a page, takes snapshots, clicks, etc., across multiple
# tool invocations within one session.
_browser: Any = None
_page: Any = None
_browser_lock = threading.Lock()


async def _ensure_browser() -> tuple[Any, Any]:
    """Return (browser, page), launching Chromium if needed."""
    global _browser, _page
    if _browser is not None and _page is not None:
        return _browser, _page

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "Playwright is not installed. "
            "Install with: pip install merkaba[browser] && python -m playwright install chromium"
        )

    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(headless=True)
    _page = await _browser.new_page()
    return _browser, _page


async def _close_browser() -> None:
    """Close the browser and clear singletons."""
    global _browser, _page
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
    _browser = None
    _page = None


# ---------------------------------------------------------------------------
# Tool implementation functions
# ---------------------------------------------------------------------------

def _browser_open(url: str) -> str:
    """Open a URL in a headless browser and return the page snapshot."""
    _validate_url(url)

    async def _run() -> str:
        _, page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        tree = await page.accessibility.snapshot()
        if tree is None:
            return f"Opened {url} (title: {title})\n[No accessibility tree available]"
        snapshot_text = format_a11y_tree(tree)
        return f"Opened {url} (title: {title})\n\n{snapshot_text}"

    return _run_async(_run())


def _browser_snapshot() -> str:
    """Take a semantic snapshot (accessibility tree) of the current page."""
    async def _run() -> str:
        _, page = await _ensure_browser()
        url = page.url
        title = await page.title()
        tree = await page.accessibility.snapshot()
        if tree is None:
            return f"Page: {url} (title: {title})\n[No accessibility tree available]"
        snapshot_text = format_a11y_tree(tree)
        return f"Page: {url} (title: {title})\n\n{snapshot_text}"

    return _run_async(_run())


def _browser_click(selector: str) -> str:
    """Click an element matching a CSS selector or text."""
    async def _run() -> str:
        _, page = await _ensure_browser()
        # Try role-based locator first (e.g. "button:Submit"), fall back to CSS
        if ":" in selector and not selector.startswith((".", "#", "[")):
            role, _, name = selector.partition(":")
            role = role.strip().lower()
            name = name.strip()
            if role in _INTERACTIVE_ROLES and name:
                await page.get_by_role(role, name=name).click(timeout=10000)
                return f"Clicked [{role}] \"{name}\""
        # Fall back to CSS selector
        await page.click(selector, timeout=10000)
        return f"Clicked element matching '{selector}'"

    return _run_async(_run())


def _browser_fill(selector: str, value: str) -> str:
    """Fill a form field identified by CSS selector, label, or placeholder."""
    async def _run() -> str:
        _, page = await _ensure_browser()
        # Try label-based locator first
        try:
            await page.get_by_label(selector).fill(value, timeout=5000)
            return f"Filled field '{selector}' with value"
        except Exception:
            pass
        # Try placeholder-based locator
        try:
            await page.get_by_placeholder(selector).fill(value, timeout=5000)
            return f"Filled field '{selector}' with value"
        except Exception:
            pass
        # Fall back to CSS selector
        await page.fill(selector, value, timeout=10000)
        return f"Filled element matching '{selector}' with value"

    return _run_async(_run())


def _browser_navigate(url: str) -> str:
    """Navigate the current browser page to a new URL."""
    _validate_url(url)

    async def _run() -> str:
        _, page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        return f"Navigated to {url} (title: {title})"

    return _run_async(_run())


def _browser_close() -> str:
    """Close the browser session."""
    async def _run() -> str:
        await _close_browser()
        return "Browser closed"

    return _run_async(_run())


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

browser_open = Tool(
    name="browser_open",
    description=(
        "Open a URL in a headless browser. Returns a semantic snapshot "
        "(accessibility tree) of the page — structured text showing all "
        "interactive elements (buttons, links, form fields) that you can "
        "then click or fill."
    ),
    function=_browser_open,
    permission_tier=PermissionTier.SENSITIVE,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to open (must be http or https)",
            },
        },
        "required": ["url"],
    },
)

browser_snapshot = Tool(
    name="browser_snapshot",
    description=(
        "Take a semantic snapshot of the current browser page. Returns the "
        "accessibility tree as structured text showing all visible elements "
        "and their roles, names, and values."
    ),
    function=_browser_snapshot,
    permission_tier=PermissionTier.MODERATE,
    parameters={
        "type": "object",
        "properties": {},
    },
)

browser_click = Tool(
    name="browser_click",
    description=(
        "Click an element on the current page. Use 'role:name' format "
        "(e.g. 'button:Submit', 'link:Sign in') for semantic targeting, "
        "or a CSS selector as fallback."
    ),
    function=_browser_click,
    permission_tier=PermissionTier.SENSITIVE,
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": (
                    "Element to click: 'role:name' (e.g. 'button:Submit') "
                    "or CSS selector (e.g. '#login-btn')"
                ),
            },
        },
        "required": ["selector"],
    },
)

browser_fill = Tool(
    name="browser_fill",
    description=(
        "Fill a form field on the current page. Tries label match first, "
        "then placeholder text, then CSS selector."
    ),
    function=_browser_fill,
    permission_tier=PermissionTier.SENSITIVE,
    parameters={
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": (
                    "Field to fill: label text, placeholder text, or CSS selector"
                ),
            },
            "value": {
                "type": "string",
                "description": "The value to fill into the field",
            },
        },
        "required": ["selector", "value"],
    },
)

browser_navigate = Tool(
    name="browser_navigate",
    description=(
        "Navigate the current browser page to a new URL. Use this after "
        "browser_open to navigate to a different page without losing the "
        "browser session."
    ),
    function=_browser_navigate,
    permission_tier=PermissionTier.SENSITIVE,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to navigate to (must be http or https)",
            },
        },
        "required": ["url"],
    },
)

browser_close = Tool(
    name="browser_close",
    description="Close the browser session and free resources.",
    function=_browser_close,
    permission_tier=PermissionTier.SAFE,
    parameters={
        "type": "object",
        "properties": {},
    },
)
