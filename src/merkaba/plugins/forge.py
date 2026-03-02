"""Skill Forge — generate merkaba plugins from skill descriptions."""

import re
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser

import httpx
import frontmatter


class UrlKind(Enum):
    CLAWHUB = "clawhub"
    GITHUB = "github"
    UNKNOWN = "unknown"


def classify_url(url: str) -> UrlKind:
    """Classify a URL as ClawHub, GitHub, or unknown."""
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS URLs are supported")
    url_lower = url.lower()
    if "clawhub.ai" in url_lower:
        return UrlKind.CLAWHUB
    if "github.com" in url_lower or "raw.githubusercontent.com" in url_lower:
        return UrlKind.GITHUB
    return UrlKind.UNKNOWN


@dataclass
class ScrapedSkill:
    """Extracted skill information from a URL."""

    name: str
    description: str
    content: str
    security_verdict: str | None = None
    security_analysis: str | None = None


def _github_blob_to_raw(url: str) -> str:
    """Convert github.com blob URL to raw.githubusercontent.com URL."""
    if "raw.githubusercontent.com" in url:
        return url
    return re.sub(
        r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)",
        r"https://raw.githubusercontent.com/\1/\2/\3",
        url,
    )


def scrape_github(url: str) -> ScrapedSkill:
    """Fetch a skill from a GitHub URL."""
    raw_url = _github_blob_to_raw(url)
    response = httpx.get(raw_url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()

    text = response.text
    post = frontmatter.loads(text)
    return ScrapedSkill(
        name=post.get("name", "unnamed"),
        description=post.get("description", ""),
        content=text,
    )


# ---------------------------------------------------------------------------
# ClawHub scraper
# ---------------------------------------------------------------------------


class _ClawHubParser(HTMLParser):
    """Extract skill info from ClawHub HTML."""

    def __init__(self):
        super().__init__()
        self._class_stack: list[str] = []
        self._in_tag: str | None = None
        self.title: str | None = None
        self.description: str = ""
        self.security_verdict: str | None = None
        self.security_analysis: str | None = None
        self._headings: list[str] = []

    def _active_class(self) -> str:
        """Return the nearest ancestor class on the stack."""
        for cls in reversed(self._class_stack):
            if cls:
                return cls
        return ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        self._in_tag = tag
        self._class_stack.append(cls)

    def handle_endtag(self, tag: str):
        self._in_tag = None
        if self._class_stack:
            self._class_stack.pop()

    def handle_data(self, data: str):
        data = data.strip()
        if not data:
            return

        active = self._active_class()

        if self._in_tag == "h1":
            self.title = data
            self._headings.append(data)
        elif "skill-description" in active:
            self.description += data + " "
        elif "verdict-value" in active:
            self.security_verdict = data
        elif "security-analysis" in active:
            if self.security_analysis is None:
                self.security_analysis = data
            else:
                self.security_analysis += " " + data

    @property
    def has_content(self) -> bool:
        """True if the page had real content (not a JS placeholder)."""
        return bool(self._headings)


def _needs_playwright_fallback(html: str) -> bool:
    """Check if the HTML is a JS placeholder needing browser rendering."""
    parser = _ClawHubParser()
    parser.feed(html)
    if not parser.has_content:
        return True
    if "Loading skill" in html and not parser.title:
        return True
    return False


def _extract_slug(url: str) -> str:
    """Extract the skill slug from a ClawHub URL."""
    parts = url.rstrip("/").split("/")
    return parts[-1]


def _scrape_clawhub_playwright(url: str) -> ScrapedSkill:
    """Render a ClawHub page with Playwright and extract skill info."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "Playwright is required for JS-rendered ClawHub pages. "
            "Install with: pip install merkaba[browser]"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()

    return _parse_clawhub_html(html, url)


def _parse_clawhub_html(html: str, url: str) -> ScrapedSkill:
    """Parse ClawHub HTML into a ScrapedSkill."""
    parser = _ClawHubParser()
    parser.feed(html)
    slug = _extract_slug(url)
    return ScrapedSkill(
        name=slug,
        description=parser.description.strip(),
        content=html,
        security_verdict=parser.security_verdict,
        security_analysis=parser.security_analysis,
    )


def scrape_clawhub(url: str) -> ScrapedSkill:
    """Fetch a skill from a ClawHub URL, with Playwright fallback for JS pages."""
    response = httpx.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()

    html = response.text

    if _needs_playwright_fallback(html):
        return _scrape_clawhub_playwright(url)

    return _parse_clawhub_html(html, url)


def scrape_url(url: str) -> ScrapedSkill:
    """Scrape a skill from a URL, dispatching to the appropriate scraper."""
    kind = classify_url(url)
    if kind == UrlKind.GITHUB:
        return scrape_github(url)
    elif kind == UrlKind.CLAWHUB:
        return scrape_clawhub(url)
    else:
        raise ValueError(f"Unsupported URL: {url}. Provide a ClawHub or GitHub URL.")


FORGE_SYSTEM_PROMPT = """You are a Merkaba plugin generator. You generate complete, original plugin content in SKILL.md format.

Merkaba is a local AI agent with these tools:
- file_read: Read file contents
- file_write: Write to files
- file_list: List files in directory
- memory_search: Search agent memory
- memory_store: Store to agent memory
- shell: Execute shell commands
- task_queue: Manage task queue
- web_fetch: Fetch web content

SKILL.md format uses YAML frontmatter:
---
name: skill-name
description: Short description
version: 0.1.0
---

# Skill Title

Skill methodology and instructions here.

IMPORTANT: Generate a complete, original merkaba plugin. Do NOT reproduce any code from the source material. Only use the description to understand the concept, then write fresh content."""


def build_generation_prompt(skill: ScrapedSkill) -> str:
    """Build the LLM generation prompt from scraped skill info."""
    parts = [
        f"Generate a complete merkaba plugin inspired by this concept:\n",
        f"Name: {skill.name}",
        f"Description: {skill.description}",
    ]

    if skill.security_verdict:
        parts.append(f"\nSecurity verdict from ClawHub: {skill.security_verdict}")
    if skill.security_analysis:
        parts.append(f"Security analysis: {skill.security_analysis}")
        parts.append("Avoid recreating any patterns flagged in the security analysis.")

    parts.append(
        "\nGenerate the SKILL.md content with proper YAML frontmatter. "
        "Include file_read, file_write, memory_search, shell tool references as appropriate. "
        "Do NOT reproduce any original code. Output ONLY the SKILL.md content."
    )

    return "\n".join(parts)


def generate_plugin(skill: ScrapedSkill) -> dict[str, str]:
    """Generate a merkaba plugin using the LLM."""
    from merkaba.llm import LLMClient  # Lazy import to avoid import-time failures

    llm = LLMClient()
    prompt = build_generation_prompt(skill)
    response = llm.chat_with_fallback(
        message=prompt,
        system_prompt=FORGE_SYSTEM_PROMPT,
        tier="complex",
    )

    if not response.content:
        raise RuntimeError("LLM returned empty response. Generation failed.")

    return {"skill_md": response.content}


def check_security_gate(skill: ScrapedSkill) -> str:
    """Check the ClawHub security verdict and return action.

    Returns: "proceed", "warn", or "double_warn"
    """
    verdict = (skill.security_verdict or "").lower()
    if verdict == "malicious":
        return "double_warn"
    if verdict == "suspicious":
        return "warn"
    return "proceed"
