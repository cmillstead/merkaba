# tests/test_web_security.py
"""Tests for SSRF protection in web_fetch tool."""
import pytest
from unittest.mock import patch, MagicMock

from merkaba.tools.builtin.web import is_url_allowed, web_fetch


class TestIsUrlAllowed:
    """Tests for the is_url_allowed function."""

    # --- Public URLs should be allowed ---

    def test_allows_public_https_url(self):
        """Public HTTPS URLs should be allowed."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            allowed, reason = is_url_allowed("https://example.com")
        assert allowed is True
        assert reason == ""

    def test_allows_public_http_url(self):
        """Public HTTP URLs should be allowed."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="8.8.8.8"):
            allowed, reason = is_url_allowed("http://example.com/page")
        assert allowed is True
        assert reason == ""

    def test_allows_url_with_port(self):
        """Public URLs with explicit ports should be allowed."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            allowed, reason = is_url_allowed("https://example.com:8443/path")
        assert allowed is True

    # --- Private IP ranges should be blocked ---

    def test_blocks_private_class_a(self):
        """Private Class A addresses (10.x.x.x) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="10.0.0.1"):
            allowed, reason = is_url_allowed("http://internal.example.com")
        assert allowed is False
        assert "10.0.0.0/8" in reason

    def test_blocks_private_class_b(self):
        """Private Class B addresses (172.16.x.x - 172.31.x.x) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="172.16.0.1"):
            allowed, reason = is_url_allowed("http://internal.example.com")
        assert allowed is False
        assert "172.16.0.0/12" in reason

    def test_blocks_private_class_c(self):
        """Private Class C addresses (192.168.x.x) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="192.168.1.1"):
            allowed, reason = is_url_allowed("http://router.local")
        assert allowed is False
        assert "192.168.0.0/16" in reason

    # --- Loopback should be blocked ---

    def test_blocks_loopback_127_0_0_1(self):
        """Loopback address 127.0.0.1 should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="127.0.0.1"):
            allowed, reason = is_url_allowed("http://localhost")
        assert allowed is False
        # Note: localhost hostname is blocked before IP check
        assert "blocked" in reason.lower()

    def test_blocks_loopback_range(self):
        """Entire loopback range (127.x.x.x) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="127.0.0.2"):
            allowed, reason = is_url_allowed("http://loopback.test")
        assert allowed is False
        assert "127.0.0.0/8" in reason

    # --- Blocked hostnames ---

    def test_blocks_localhost_hostname(self):
        """Hostname 'localhost' should be blocked."""
        allowed, reason = is_url_allowed("http://localhost/admin")
        assert allowed is False
        assert "localhost" in reason.lower()

    def test_blocks_localhost_case_insensitive(self):
        """Hostname blocking should be case-insensitive."""
        allowed, reason = is_url_allowed("http://LOCALHOST/admin")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_blocks_google_metadata(self):
        """Google Cloud metadata endpoint should be blocked."""
        allowed, reason = is_url_allowed("http://metadata.google.internal/computeMetadata/v1/")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_blocks_aws_metadata_hostname(self):
        """AWS metadata hostname should be blocked."""
        allowed, reason = is_url_allowed("http://metadata.aws.internal/")
        assert allowed is False
        assert "blocked" in reason.lower()

    # --- Cloud metadata IP (link-local) should be blocked ---

    def test_blocks_aws_metadata_ip(self):
        """AWS metadata IP (169.254.169.254) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="169.254.169.254"):
            allowed, reason = is_url_allowed("http://aws-metadata.example.com")
        assert allowed is False
        assert "169.254.0.0/16" in reason

    def test_blocks_link_local_range(self):
        """Link-local range (169.254.x.x) should be blocked."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="169.254.1.1"):
            allowed, reason = is_url_allowed("http://link-local.test")
        assert allowed is False
        assert "169.254.0.0/16" in reason

    # --- Invalid schemes should be blocked ---

    def test_blocks_file_scheme(self):
        """file:// scheme should be blocked."""
        allowed, reason = is_url_allowed("file:///etc/passwd")
        assert allowed is False
        assert "scheme" in reason.lower()
        assert "file" in reason.lower()

    def test_blocks_ftp_scheme(self):
        """ftp:// scheme should be blocked."""
        allowed, reason = is_url_allowed("ftp://ftp.example.com/file.txt")
        assert allowed is False
        assert "scheme" in reason.lower()
        assert "ftp" in reason.lower()

    def test_blocks_gopher_scheme(self):
        """gopher:// scheme should be blocked."""
        allowed, reason = is_url_allowed("gopher://gopher.example.com/")
        assert allowed is False
        assert "scheme" in reason.lower()

    def test_blocks_dict_scheme(self):
        """dict:// scheme should be blocked."""
        allowed, reason = is_url_allowed("dict://dict.example.com/")
        assert allowed is False
        assert "scheme" in reason.lower()

    # --- Edge cases ---

    def test_blocks_url_without_scheme(self):
        """URL without scheme should be blocked."""
        allowed, reason = is_url_allowed("example.com")
        assert allowed is False
        # Empty scheme is not in allowed schemes
        assert "scheme" in reason.lower()

    def test_blocks_url_without_hostname(self):
        """URL without hostname should be blocked."""
        allowed, reason = is_url_allowed("http:///path")
        assert allowed is False
        assert "hostname" in reason.lower()

    def test_handles_dns_resolution_failure(self):
        """Should handle DNS resolution failures gracefully."""
        import socket
        with patch(
            "merkaba.tools.builtin.web.socket.gethostbyname",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            allowed, reason = is_url_allowed("http://nonexistent.invalid")
        assert allowed is False
        assert "resolve" in reason.lower()


class TestWebFetchSsrfProtection:
    """Tests for SSRF protection in web_fetch tool."""

    def test_web_fetch_blocks_private_ip(self):
        """web_fetch should reject requests to private IPs."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="192.168.1.1"):
            result = web_fetch.execute(url="http://internal.company.com/api")

        assert not result.success
        assert "not allowed" in result.error.lower()

    def test_web_fetch_blocks_localhost(self):
        """web_fetch should reject requests to localhost."""
        result = web_fetch.execute(url="http://localhost:8080/admin")

        assert not result.success
        assert "not allowed" in result.error.lower()

    def test_web_fetch_blocks_metadata_endpoint(self):
        """web_fetch should reject requests to cloud metadata endpoints."""
        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="169.254.169.254"):
            result = web_fetch.execute(url="http://169.254.169.254/latest/meta-data/")

        assert not result.success
        assert "not allowed" in result.error.lower()

    def test_web_fetch_allows_public_url(self):
        """web_fetch should allow requests to public URLs."""
        mock_response = MagicMock()
        mock_response.text = "<html>Hello</html>"
        mock_response.raise_for_status = MagicMock()

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value="93.184.216.34"):
            with patch("merkaba.tools.builtin.web.httpx.get", return_value=mock_response):
                result = web_fetch.execute(url="https://example.com")

        assert result.success
        assert "Hello" in result.output

    def test_web_fetch_blocks_file_scheme(self):
        """web_fetch should reject file:// URLs."""
        result = web_fetch.execute(url="file:///etc/passwd")

        assert not result.success
        assert "not allowed" in result.error.lower()


class TestSsrfDnsRebindingNote:
    """
    Note: DNS rebinding attacks cannot be fully prevented at this layer.

    In a DNS rebinding attack, an attacker's DNS server returns a public IP
    on the first query (passing our check), then a private IP on subsequent
    queries (used by the actual HTTP request).

    Mitigations that could be added in the future:
    1. Resolve DNS once and connect directly to that IP
    2. Use a DNS resolver that prevents rebinding
    3. Implement request-time IP validation in a custom HTTP transport

    The current implementation provides basic protection against direct SSRF
    attempts, which covers the most common attack vectors.
    """

    def test_documentation_note_for_dns_rebinding(self):
        """This test documents that DNS rebinding protection is limited."""
        # This test exists purely for documentation purposes
        # The docstring above explains the limitation
        pass
