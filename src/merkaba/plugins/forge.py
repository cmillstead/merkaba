"""Skill Forge — generate merkaba plugins from skill descriptions."""

import re
from dataclasses import dataclass
from enum import Enum

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
