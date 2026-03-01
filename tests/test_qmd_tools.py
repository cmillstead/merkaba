# tests/test_qmd_tools.py
"""Tests for QMD document search/get agent tools."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_urlopen():
    with patch("merkaba.integrations.qmd_adapter.urlopen") as mock:
        yield mock


def _make_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestDocumentSearchTool:
    def test_tool_exists(self):
        from merkaba.tools.builtin.qmd import document_search
        assert document_search.name == "document_search"

    def test_tool_is_safe_tier(self):
        from merkaba.tools.builtin.qmd import document_search
        from merkaba.tools.base import PermissionTier
        assert document_search.permission_tier == PermissionTier.SAFE

    def test_search_executes(self, mock_urlopen):
        # Mock health check for connect
        health_resp = _make_response({"status": "ok"})
        search_resp = _make_response({"result": [{"id": "a", "score": 0.9, "fields": {"path": "test.md", "text": "content"}}]})
        mock_urlopen.side_effect = [health_resp, search_resp]

        from merkaba.tools.builtin.qmd import document_search
        result = document_search.execute(query="test")
        assert result.success is True

    def test_search_daemon_down(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        from merkaba.tools.builtin.qmd import document_search
        result = document_search.execute(query="test")
        # Should return graceful error, not crash
        assert result.success is True
        assert "unavailable" in result.output.lower() or "error" in result.output.lower()


class TestDocumentGetTool:
    def test_tool_exists(self):
        from merkaba.tools.builtin.qmd import document_get
        assert document_get.name == "document_get"

    def test_tool_is_safe_tier(self):
        from merkaba.tools.builtin.qmd import document_get
        from merkaba.tools.base import PermissionTier
        assert document_get.permission_tier == PermissionTier.SAFE

    def test_get_executes(self, mock_urlopen):
        health_resp = _make_response({"status": "ok"})
        get_resp = _make_response({"result": {"fields": {"path": "test.md", "text": "Full content"}}})
        mock_urlopen.side_effect = [health_resp, get_resp]

        from merkaba.tools.builtin.qmd import document_get
        result = document_get.execute(path="test.md")
        assert result.success is True
