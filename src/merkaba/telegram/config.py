"""Telegram configuration management."""

import json
import os
from dataclasses import dataclass


@dataclass
class TelegramConfig:
    """Manages Telegram bot configuration."""

    config_path: str | None = None

    def __post_init__(self):
        if self.config_path is None:
            self.config_path = os.path.expanduser("~/.friday/config.json")
        self._ensure_config_exists()

    def _ensure_config_exists(self):
        """Create config file if it doesn't exist."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as f:
                json.dump({}, f)

    def _load(self) -> dict:
        """Load config from file."""
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict):
        """Save config to file."""
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_bot_token(self) -> str | None:
        """Get Telegram bot token."""
        data = self._load()
        return data.get("telegram", {}).get("bot_token")

    def save_bot_token(self, token: str):
        """Save Telegram bot token."""
        data = self._load()
        if "telegram" not in data:
            data["telegram"] = {}
        data["telegram"]["bot_token"] = token
        self._save(data)

    def get_allowed_user_ids(self) -> list[int]:
        """Get list of allowed Telegram user IDs."""
        data = self._load()
        return data.get("telegram", {}).get("allowed_user_ids", [])

    def save_allowed_user_ids(self, user_ids: list[int]):
        """Save allowed Telegram user IDs."""
        data = self._load()
        if "telegram" not in data:
            data["telegram"] = {}
        data["telegram"]["allowed_user_ids"] = user_ids
        self._save(data)

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user ID is allowed."""
        return user_id in self.get_allowed_user_ids()

    def is_configured(self) -> bool:
        """Check if Telegram is fully configured."""
        return self.get_bot_token() is not None and len(self.get_allowed_user_ids()) > 0
