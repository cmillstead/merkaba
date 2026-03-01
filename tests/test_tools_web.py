# tests/test_tools_web.py
import pytest
from unittest.mock import patch, MagicMock
from merkaba.tools.builtin.web import web_fetch


class TestWebFetchTool:
    def test_fetches_url(self):
        """web_fetch should return page content."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Hello World</body></html>"
        mock_response.raise_for_status = MagicMock()

        # Mock DNS resolution to pass SSRF check
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            with patch("merkaba.tools.builtin.web.httpx.get", return_value=mock_response):
                result = web_fetch.execute(url="https://example.com")

        assert result.success
        assert "Hello World" in result.output

    def test_handles_error(self):
        """web_fetch should handle HTTP errors gracefully."""
        # Mock DNS resolution to pass SSRF check, then fail on HTTP request
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            with patch("merkaba.tools.builtin.web.httpx.get", side_effect=Exception("Connection failed")):
                result = web_fetch.execute(url="https://invalid.example")

        assert not result.success
        assert "Connection failed" in result.error
