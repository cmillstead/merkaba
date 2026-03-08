"""Per-business prompt file loader with fallback chain."""

import os
from pathlib import Path

DEFAULT_SOUL = """You are Merkaba, an autonomous AI agent evolving toward running multiple businesses independently.

## Who You Are
- A local AI system running on your owner's Mac (always on, private, no cloud dependency)
- Powered by local LLMs via Ollama
- Named after the tradition of AI assistants that grow into trusted partners

## How to Behave
- Be direct and concise — no fluff
- When unsure, ask rather than guess
- For significant actions, use the approval workflow
- Track what works and what doesn't — learnings compound
- You're a partner, not a servant — have opinions backed by data
- ALWAYS check your memory first before doing web research or file searches
"""

DEFAULT_USER = """## Your Owner
- Building digital product businesses
- Wants you to eventually run businesses with graduated autonomy
- Values: privacy, local-first, incremental trust, practical results
"""


class PromptLoader:
    """Loads SOUL.md and USER.md with per-business fallback."""

    def __init__(self, base_dir: str | None = None):
        from merkaba.paths import merkaba_home as _merkaba_home
        self.base_dir = Path(base_dir or _merkaba_home())

    def _read_file(self, path: Path) -> str | None:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return None

    def load(self, business_id: int | None = None) -> tuple[str, str]:
        """Load (soul, user) with fallback: business > global > builtin."""
        soul = None
        user = None

        if business_id is not None:
            biz_dir = self.base_dir / "businesses" / str(business_id)
            soul = self._read_file(biz_dir / "SOUL.md")
            user = self._read_file(biz_dir / "USER.md")

        if soul is None:
            soul = self._read_file(self.base_dir / "SOUL.md")
        if user is None:
            user = self._read_file(self.base_dir / "USER.md")

        return (soul or DEFAULT_SOUL, user or DEFAULT_USER)

    def resolve(self, business_id: int | None = None) -> dict:
        """Show which files won in the fallback chain."""
        info = {"soul_source": "builtin", "user_source": "builtin"}

        if business_id is not None:
            biz_dir = self.base_dir / "businesses" / str(business_id)
            if (biz_dir / "SOUL.md").is_file():
                info["soul_source"] = "business"
            if (biz_dir / "USER.md").is_file():
                info["user_source"] = "business"

        if info["soul_source"] == "builtin" and (self.base_dir / "SOUL.md").is_file():
            info["soul_source"] = "global"
        if info["user_source"] == "builtin" and (self.base_dir / "USER.md").is_file():
            info["user_source"] = "global"

        return info

    def seed(self) -> None:
        """Create default SOUL.md and USER.md if they don't exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        soul_path = self.base_dir / "SOUL.md"
        user_path = self.base_dir / "USER.md"
        if not soul_path.exists():
            soul_path.write_text(DEFAULT_SOUL, encoding="utf-8")
        if not user_path.exists():
            user_path.write_text(DEFAULT_USER, encoding="utf-8")
