"""Skill Forge — generate merkaba plugins from skill descriptions."""

from enum import Enum


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
