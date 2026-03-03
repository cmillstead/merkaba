# tests/test_tools_web.py
import pytest
from unittest.mock import patch, MagicMock, call
from merkaba.tools.builtin.web import web_fetch, _web_fetch


class TestWebFetchTool:
    def test_fetches_url(self):
        """web_fetch should return page content."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Hello World</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

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


class TestWebFetchRedirects:
    """Tests for the SSRF-safe manual redirect handling in _web_fetch."""

    def test_web_fetch_blocks_redirect_to_internal(self):
        """A redirect to an internal/loopback IP must raise ValueError."""
        # First response: 302 pointing to a loopback address
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "http://127.0.0.1/secret"}

        def _get_side_effect(url, **kwargs):
            return redirect_response

        def _resolve(hostname):
            # Return the hostname unchanged for IP literals (including 127.0.0.1)
            # so that the SSRF check correctly identifies the loopback range.
            # For named hosts like example.com return a safe public IP.
            import ipaddress
            try:
                ipaddress.ip_address(hostname)
                return hostname  # Already an IP — return as-is
            except ValueError:
                return "93.184.216.34"

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", side_effect=_resolve):
            with patch("merkaba.tools.builtin.web.httpx.get", side_effect=_get_side_effect):
                with pytest.raises(ValueError, match="blocked"):
                    _web_fetch("https://example.com/redirect-to-internal")

    def test_web_fetch_follows_safe_redirect(self):
        """A redirect to a safe external URL should be followed and return content."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "https://example.org/page"}

        final_response = MagicMock()
        final_response.status_code = 200
        final_response.text = "Safe content"
        final_response.raise_for_status = MagicMock()

        responses = iter([redirect_response, final_response])

        def _get_side_effect(url, **kwargs):
            return next(responses)

        # Both hostnames resolve to public IPs
        def _resolve(hostname):
            return "93.184.216.34"

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", side_effect=_resolve):
            with patch("merkaba.tools.builtin.web.httpx.get", side_effect=_get_side_effect):
                result = _web_fetch("https://example.com/redirect")

        assert result == "Safe content"

    def test_web_fetch_max_redirects(self):
        """More than 5 consecutive redirects must raise ValueError."""
        def _make_redirect(target: str) -> MagicMock:
            r = MagicMock()
            r.status_code = 302
            r.headers = {"location": target}
            return r

        # 6 redirects — exceeds the limit of 5
        redirect_responses = [
            _make_redirect("https://hop1.example.com/"),
            _make_redirect("https://hop2.example.com/"),
            _make_redirect("https://hop3.example.com/"),
            _make_redirect("https://hop4.example.com/"),
            _make_redirect("https://hop5.example.com/"),
            _make_redirect("https://hop6.example.com/"),
        ]
        responses = iter(redirect_responses)

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            with patch("merkaba.tools.builtin.web.httpx.get", side_effect=lambda url, **kw: next(responses)):
                with pytest.raises(ValueError, match="Too many redirects"):
                    _web_fetch("https://start.example.com/")
