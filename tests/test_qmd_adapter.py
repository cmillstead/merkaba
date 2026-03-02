# tests/test_qmd_adapter.py
"""Tests for QMD document search adapter."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from merkaba.integrations.base import ADAPTER_REGISTRY


def test_qmd_adapter_registered():
    from merkaba.integrations import qmd_adapter  # noqa: F401
    assert "qmd" in ADAPTER_REGISTRY


# --- Fixtures ---


@pytest.fixture
def adapter():
    from merkaba.integrations.qmd_adapter import QMDAdapter
    return QMDAdapter(name="qmd")


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen for HTTP calls."""
    with patch("merkaba.integrations.qmd_adapter.urlopen") as mock:
        yield mock


def _make_response(data: dict, status: int = 200) -> MagicMock:
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# --- connect ---


class TestConnect:
    def test_connect_success(self, adapter, mock_urlopen):
        mock_urlopen.return_value = _make_response({"status": "ok"})
        assert adapter.connect() is True
        assert adapter.is_connected is True

    def test_connect_failure(self, adapter, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        assert adapter.connect() is False
        assert adapter.is_connected is False


# --- health_check ---


class TestHealthCheck:
    def test_health_check_ok(self, adapter, mock_urlopen):
        mock_urlopen.return_value = _make_response({"status": "ok"})
        adapter._connected = True
        result = adapter.health_check()
        assert result["ok"] is True
        assert result["adapter"] == "qmd"

    def test_health_check_not_connected(self, adapter, mock_urlopen):
        result = adapter.health_check()
        assert result["ok"] is False


# --- execute: search ---


class TestSearch:
    def test_search_returns_results(self, adapter, mock_urlopen):
        adapter._connected = True
        search_response = {
            "result": [
                {"id": "abc123", "score": 0.85, "fields": {"path": "notes/test.md", "text": "Test content"}},
                {"id": "def456", "score": 0.72, "fields": {"path": "docs/readme.md", "text": "Readme content"}},
            ]
        }
        mock_urlopen.return_value = _make_response(search_response)
        result = adapter.execute("search", {"query": "test query", "limit": 5})
        assert result["ok"] is True
        assert len(result["results"]) == 2

    def test_search_missing_query(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("search", {})
        assert result["ok"] is False
        assert "query" in result["error"].lower()

    def test_search_not_connected(self, adapter, mock_urlopen):
        result = adapter.execute("search", {"query": "test"})
        assert result["ok"] is False
        assert "not connected" in result["error"].lower()


# --- execute: get ---


class TestGet:
    def test_get_by_path(self, adapter, mock_urlopen):
        adapter._connected = True
        get_response = {
            "result": {"id": "abc123", "fields": {"path": "notes/test.md", "text": "Full document content here"}}
        }
        mock_urlopen.return_value = _make_response(get_response)
        result = adapter.execute("get", {"path": "notes/test.md"})
        assert result["ok"] is True
        assert "content" in result

    def test_get_missing_path(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("get", {})
        assert result["ok"] is False
        assert "path" in result["error"].lower()


# --- execute: status ---


class TestStatus:
    def test_status_returns_info(self, adapter, mock_urlopen):
        adapter._connected = True
        status_response = {"status": "ok", "collections": 2, "documents": 150}
        mock_urlopen.return_value = _make_response(status_response)
        result = adapter.execute("status", {})
        assert result["ok"] is True

    def test_unknown_action(self, adapter, mock_urlopen):
        adapter._connected = True
        result = adapter.execute("unknown_action", {})
        assert result["ok"] is False
        assert "unknown" in result["error"].lower()


# --- HTTP error handling ---


class TestErrorHandling:
    def test_http_error(self, adapter, mock_urlopen):
        adapter._connected = True
        mock_urlopen.side_effect = Exception("HTTP 500")
        result = adapter.execute("status", {})
        assert result["ok"] is False

    def test_malformed_json(self, adapter, mock_urlopen):
        adapter._connected = True
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"not json"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        result = adapter.execute("status", {})
        assert result["ok"] is False


# --- Async wrappers ---


class TestAsyncWrappers:
    """Tests for async variants of QMD adapter methods."""

    def test_request_async(self, adapter, mock_urlopen):
        mock_urlopen.return_value = _make_response({"status": "ok"})
        result = asyncio.get_event_loop().run_until_complete(
            adapter._request_async("GET", "/health")
        )
        assert result == {"status": "ok"}

    def test_search_async(self, adapter, mock_urlopen):
        adapter._connected = True
        search_response = {
            "result": [
                {"id": "abc", "score": 0.9, "fields": {"path": "a.md", "text": "hi"}},
            ]
        }
        mock_urlopen.return_value = _make_response(search_response)
        result = asyncio.get_event_loop().run_until_complete(
            adapter._search_async({"query": "hello", "limit": 3})
        )
        assert result["ok"] is True
        assert result["count"] == 1

    def test_search_async_missing_query(self, adapter, mock_urlopen):
        adapter._connected = True
        result = asyncio.get_event_loop().run_until_complete(
            adapter._search_async({})
        )
        assert result["ok"] is False
        assert "query" in result["error"].lower()

    def test_get_async(self, adapter, mock_urlopen):
        adapter._connected = True
        get_response = {
            "result": {"id": "x", "fields": {"path": "b.md", "text": "content"}}
        }
        mock_urlopen.return_value = _make_response(get_response)
        result = asyncio.get_event_loop().run_until_complete(
            adapter._get_async({"path": "b.md"})
        )
        assert result["ok"] is True
        assert result["content"] == "content"

    def test_get_async_missing_path(self, adapter, mock_urlopen):
        adapter._connected = True
        result = asyncio.get_event_loop().run_until_complete(
            adapter._get_async({})
        )
        assert result["ok"] is False
        assert "path" in result["error"].lower()

    def test_status_async(self, adapter, mock_urlopen):
        adapter._connected = True
        mock_urlopen.return_value = _make_response({"collections": 2})
        result = asyncio.get_event_loop().run_until_complete(
            adapter._status_async({})
        )
        assert result["ok"] is True

    def test_execute_async(self, adapter, mock_urlopen):
        adapter._connected = True
        search_response = {
            "result": [
                {"id": "z", "score": 0.8, "fields": {"path": "c.md", "text": "yo"}},
            ]
        }
        mock_urlopen.return_value = _make_response(search_response)
        result = asyncio.get_event_loop().run_until_complete(
            adapter.execute_async("search", {"query": "yo"})
        )
        assert result["ok"] is True
        assert result["count"] == 1

    def test_execute_async_not_connected(self, adapter, mock_urlopen):
        result = asyncio.get_event_loop().run_until_complete(
            adapter.execute_async("search", {"query": "test"})
        )
        assert result["ok"] is False
        assert "not connected" in result["error"].lower()

    def test_request_async_error(self, adapter, mock_urlopen):
        adapter._connected = True
        mock_urlopen.side_effect = Exception("Connection refused")
        result = asyncio.get_event_loop().run_until_complete(
            adapter._status_async({})
        )
        assert result["ok"] is False
