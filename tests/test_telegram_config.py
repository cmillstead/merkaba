"""Tests for Telegram config management."""

import json
import os
import tempfile
import pytest
from merkaba.telegram.config import TelegramConfig


class TestTelegramConfig:
    """Tests for TelegramConfig class."""

    def test_config_loads_telegram_settings(self):
        """TelegramConfig should load bot_token and allowed_user_ids."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump({
                    "telegram": {
                        "bot_token": "123:ABC",
                        "allowed_user_ids": [111, 222]
                    }
                }, f)

            config = TelegramConfig(config_path)
            assert config.get_bot_token() == "123:ABC"
            assert config.get_allowed_user_ids() == [111, 222]

    def test_config_returns_none_when_not_configured(self):
        """TelegramConfig should return None when telegram not configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump({}, f)

            config = TelegramConfig(config_path)
            assert config.get_bot_token() is None
            assert config.get_allowed_user_ids() == []

    def test_save_bot_token(self):
        """TelegramConfig should save bot token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")

            config = TelegramConfig(config_path)
            config.save_bot_token("new_token")

            assert config.get_bot_token() == "new_token"

    def test_save_allowed_user_ids(self):
        """TelegramConfig should save allowed user IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")

            config = TelegramConfig(config_path)
            config.save_allowed_user_ids([123456])

            assert config.get_allowed_user_ids() == [123456]

    def test_is_user_allowed(self):
        """is_user_allowed should check if user ID is in allowed list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump({
                    "telegram": {
                        "bot_token": "token",
                        "allowed_user_ids": [111, 222]
                    }
                }, f)

            config = TelegramConfig(config_path)
            assert config.is_user_allowed(111) is True
            assert config.is_user_allowed(999) is False
