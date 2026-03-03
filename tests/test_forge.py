# tests/test_forge.py
"""Tests for _forge_fetch SSRF protection in forge.py."""

import pytest
from unittest.mock import MagicMock, patch

try:
    from merkaba.plugins.forge import _forge_fetch, FORGE_ALLOWED_DOMAINS
    HAS_DEPENDENCIES = True
except ImportError as _e:
    HAS_DEPENDENCIES = False
    _IMPORT_ERROR = str(_e)
    _forge_fetch = None
    FORGE_ALLOWED_DOMAINS = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {_IMPORT_ERROR if not HAS_DEPENDENCIES else ''}",
)

_PUBLIC_IP = "140.82.121.3"


class TestForgeFetch:
    """SSRF protection tests for _forge_fetch."""

    def test_forge_fetch_blocks_disallowed_domain(self):
        """A domain not in FORGE_ALLOWED_DOMAINS must raise ValueError immediately."""
        with pytest.raises(ValueError, match="allowed domain"):
            _forge_fetch("https://evil.example.com/malicious-skill")

    def test_forge_fetch_blocks_ssrf_redirect(self):
        """A redirect from an allowed domain to an internal IP must raise ValueError."""
        # The initial URL passes the domain allowlist (clawhub.ai is allowed).
        # The redirect points to 127.0.0.1 which is in the SSRF blocked ranges.
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "http://127.0.0.1/steal-secrets"}

        def _side_effect(url, **kwargs):
            return redirect_response

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP):
            with patch("merkaba.plugins.forge.httpx.get", side_effect=_side_effect):
                with pytest.raises(ValueError, match="blocked"):
                    _forge_fetch("https://clawhub.ai/skills/some-skill")

    def test_forge_fetch_blocks_redirect_to_disallowed_domain(self):
        """A redirect from an allowed domain to a non-allowlisted domain must raise ValueError."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "https://attacker.example.com/payload"}

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP):
            with patch("merkaba.plugins.forge.httpx.get", return_value=redirect_response):
                with pytest.raises(ValueError, match="allowed domain"):
                    _forge_fetch("https://clawhub.ai/skills/some-skill")

    def test_forge_fetch_follows_allowed_redirect(self):
        """A redirect that stays within the allowed domains and passes SSRF check succeeds."""
        redirect_response = MagicMock()
        redirect_response.status_code = 301
        redirect_response.headers = {"location": "https://clawhub.ai/skills/real-slug"}

        final_response = MagicMock()
        final_response.status_code = 200

        responses = iter([redirect_response, final_response])

        with patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP):
            with patch("merkaba.plugins.forge.httpx.get", side_effect=lambda url, **kw: next(responses)):
                result = _forge_fetch("https://clawhub.ai/skills/some-skill")

        assert result.status_code == 200

    def test_forge_fetch_allowed_domains_set(self):
        """FORGE_ALLOWED_DOMAINS contains the expected domains."""
        assert "github.com" in FORGE_ALLOWED_DOMAINS
        assert "raw.githubusercontent.com" in FORGE_ALLOWED_DOMAINS
        assert "clawhub.ai" in FORGE_ALLOWED_DOMAINS
