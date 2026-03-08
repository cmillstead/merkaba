# tests/test_config_utils.py
"""Unit tests for merkaba.config.utils — atomic writes and secret masking."""

import json
import os

import pytest

from merkaba.config.utils import atomic_write_json, deep_mask_secrets


class TestAtomicWriteJson:
    """Tests for atomic_write_json()."""

    def test_writes_valid_json(self, tmp_path):
        path = str(tmp_path / "test.json")
        data = {"key": "value", "nested": {"a": 1}}
        atomic_write_json(path, data)

        with open(path) as f:
            result = json.load(f)
        assert result == data

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "dir" / "test.json")
        atomic_write_json(path, {"ok": True})

        assert os.path.isfile(path)
        with open(path) as f:
            assert json.load(f) == {"ok": True}

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "test.json")
        atomic_write_json(path, {"version": 1})
        atomic_write_json(path, {"version": 2})

        with open(path) as f:
            assert json.load(f)["version"] == 2

    def test_no_temp_file_on_success(self, tmp_path):
        path = str(tmp_path / "test.json")
        atomic_write_json(path, {"ok": True})

        # No .tmp files should remain
        tmp_files = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
        assert tmp_files == []


class TestDeepMaskSecrets:
    """Tests for deep_mask_secrets()."""

    def test_masks_top_level_api_key(self):
        config = {"api_key": "sk-very-long-secret-key"}
        result = deep_mask_secrets(config)
        assert result["api_key"] == "sk-v***"
        # Original unchanged
        assert config["api_key"] == "sk-very-long-secret-key"

    def test_masks_nested_api_keys(self):
        config = {
            "cloud_providers": {
                "anthropic": {"api_key": "sk-ant-secret-key-5678", "model": "claude-3"},
                "openai": {"api_key": "sk-openai-secret-9012"},
            }
        }
        result = deep_mask_secrets(config)
        assert "***" in result["cloud_providers"]["anthropic"]["api_key"]
        assert "sk-ant-secret-key-5678" not in json.dumps(result)
        assert result["cloud_providers"]["anthropic"]["model"] == "claude-3"

    def test_masks_short_keys(self):
        config = {"api_key": "sh"}
        result = deep_mask_secrets(config)
        assert result["api_key"] == "***"

    def test_masks_multiple_secret_key_names(self):
        config = {
            "password": "hunter2-long-pass",
            "encryption_key": "enc-key-very-long",
            "totp_secret": "totp-secret-long!",
            "normal_key": "visible",
        }
        result = deep_mask_secrets(config)
        assert "***" in result["password"]
        assert "***" in result["encryption_key"]
        assert "***" in result["totp_secret"]
        assert result["normal_key"] == "visible"

    def test_deep_copy_prevents_mutation(self):
        original = {
            "api_key": "original-secret",
            "nested": {"api_key": "nested-secret"},
        }
        result = deep_mask_secrets(original)
        assert original["api_key"] == "original-secret"
        assert original["nested"]["api_key"] == "nested-secret"
        assert "***" in result["api_key"]
        assert "***" in result["nested"]["api_key"]

    def test_handles_non_string_values(self):
        config = {"api_key": 12345, "password": None, "token": True}
        result = deep_mask_secrets(config)
        # Non-string values should pass through unchanged
        assert result["api_key"] == 12345
        assert result["password"] is None
        assert result["token"] is True

    def test_empty_config(self):
        assert deep_mask_secrets({}) == {}
