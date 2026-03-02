# tests/test_plugin_forge.py
import pytest
from unittest.mock import MagicMock, patch

try:
    from merkaba.plugins.forge import classify_url, UrlKind
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    classify_url = None
    UrlKind = None

try:
    from merkaba.plugins.forge import scrape_github, ScrapedSkill
except ImportError:
    scrape_github = None
    ScrapedSkill = None

try:
    from merkaba.plugins.forge import scrape_clawhub
except ImportError:
    scrape_clawhub = None

try:
    from merkaba.plugins.forge import scrape_url
except ImportError:
    scrape_url = None

try:
    from merkaba.plugins.forge import check_security_gate
except ImportError:
    check_security_gate = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestClassifyUrl:
    def test_clawhub_skill_url(self):
        url = "https://clawhub.ai/skills/some-skill-name"
        assert classify_url(url) == UrlKind.CLAWHUB

    def test_clawhub_with_org(self):
        url = "https://clawhub.ai/org/some-org/skills/my-skill"
        assert classify_url(url) == UrlKind.CLAWHUB

    def test_github_url(self):
        url = "https://github.com/user/repo/blob/main/skills/my-skill/SKILL.md"
        assert classify_url(url) == UrlKind.GITHUB

    def test_github_raw_url(self):
        url = "https://raw.githubusercontent.com/user/repo/main/SKILL.md"
        assert classify_url(url) == UrlKind.GITHUB

    def test_unknown_url(self):
        url = "https://example.com/some-page"
        assert classify_url(url) == UrlKind.UNKNOWN

    def test_rejects_non_https(self):
        with pytest.raises(ValueError, match="HTTPS"):
            classify_url("http://clawhub.ai/skills/test")


class TestScrapeGithub:
    def test_fetches_raw_content(self):
        mock_resp = MagicMock()
        mock_resp.text = """---
name: test-skill
description: A test skill for demos
---
# Test Skill

Use this to test things.
"""
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp) as mock_get:
            result = scrape_github("https://github.com/user/repo/blob/main/skills/test/SKILL.md")

        assert result.name == "test-skill"
        assert "test skill" in result.description.lower()
        # Converts blob URL to raw URL
        call_url = mock_get.call_args[0][0]
        assert "raw.githubusercontent.com" in call_url

    def test_raw_url_passed_directly(self):
        mock_resp = MagicMock()
        mock_resp.text = "---\nname: s\ndescription: d\n---\ncontent"
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp) as mock_get:
            scrape_github("https://raw.githubusercontent.com/user/repo/main/SKILL.md")

        call_url = mock_get.call_args[0][0]
        assert call_url == "https://raw.githubusercontent.com/user/repo/main/SKILL.md"

    def test_http_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                scrape_github("https://github.com/user/repo/blob/main/SKILL.md")


SAMPLE_CLAWHUB_HTML = """
<html>
<head><title>My Skill - ClawHub</title></head>
<body>
<h1>My Awesome Skill</h1>
<div class="skill-description">
<p>This skill helps automate code reviews by analyzing diffs.</p>
</div>
<div class="security-verdict">
<span class="verdict-label">Overall Assessment:</span>
<span class="verdict-value">Benign</span>
</div>
<div class="security-analysis">
<p>No dangerous patterns found. Standard file operations only.</p>
</div>
</body>
</html>
"""

SAMPLE_CLAWHUB_JS_PLACEHOLDER = """
<html>
<head><title>ClawHub</title></head>
<body>
<div id="app">Loading skill...</div>
<script src="/app.js"></script>
</body>
</html>
"""


class TestScrapeClawhub:
    def test_extracts_from_html(self):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_CLAWHUB_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            result = scrape_clawhub("https://clawhub.ai/skills/my-awesome-skill")

        assert result.name == "my-awesome-skill"
        assert "code reviews" in result.description.lower()
        assert result.security_verdict == "Benign"

    def test_extracts_security_analysis(self):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_CLAWHUB_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            result = scrape_clawhub("https://clawhub.ai/skills/my-awesome-skill")

        assert result.security_analysis is not None
        assert "No dangerous patterns" in result.security_analysis

    def test_js_placeholder_triggers_playwright_fallback(self):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_CLAWHUB_JS_PLACEHOLDER
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            with patch("merkaba.plugins.forge._scrape_clawhub_playwright") as mock_pw:
                mock_pw.return_value = ScrapedSkill(
                    name="my-skill", description="A skill", content="...",
                    security_verdict="Benign", security_analysis="Clean"
                )
                result = scrape_clawhub("https://clawhub.ai/skills/my-skill")

        mock_pw.assert_called_once()
        assert result.name == "my-skill"

    def test_no_heading_triggers_playwright_fallback(self):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><p>no heading here</p></body></html>"
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            with patch("merkaba.plugins.forge._scrape_clawhub_playwright") as mock_pw:
                mock_pw.return_value = ScrapedSkill(
                    name="test", description="d", content="c"
                )
                scrape_clawhub("https://clawhub.ai/skills/test")

        mock_pw.assert_called_once()

    def test_playwright_not_installed_raises(self):
        """When Playwright fallback is needed but not installed."""
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_CLAWHUB_JS_PLACEHOLDER
        mock_resp.raise_for_status = MagicMock()

        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_resp):
            with patch("merkaba.plugins.forge._scrape_clawhub_playwright",
                       side_effect=ImportError("pip install merkaba[browser]")):
                with pytest.raises(ImportError, match="browser"):
                    scrape_clawhub("https://clawhub.ai/skills/test")


class TestScrapeUrl:
    def test_dispatches_github(self):
        with patch("merkaba.plugins.forge.scrape_github") as mock_gh:
            mock_gh.return_value = ScrapedSkill(name="s", description="d", content="c")
            result = scrape_url("https://github.com/user/repo/blob/main/SKILL.md")
        mock_gh.assert_called_once()

    def test_dispatches_clawhub(self):
        with patch("merkaba.plugins.forge.scrape_clawhub") as mock_ch:
            mock_ch.return_value = ScrapedSkill(name="s", description="d", content="c")
            result = scrape_url("https://clawhub.ai/skills/test")
        mock_ch.assert_called_once()

    def test_unknown_url_raises(self):
        with pytest.raises(ValueError, match="Unsupported URL"):
            scrape_url("https://example.com/page")

    def test_non_https_raises(self):
        with pytest.raises(ValueError, match="HTTPS"):
            scrape_url("http://clawhub.ai/skills/test")


class TestSecurityGate:
    def test_benign_passes(self):
        skill = ScrapedSkill(name="s", description="d", content="c", security_verdict="Benign")
        assert check_security_gate(skill) == "proceed"

    def test_suspicious_warns(self):
        skill = ScrapedSkill(name="s", description="d", content="c", security_verdict="Suspicious")
        assert check_security_gate(skill) == "warn"

    def test_malicious_blocks(self):
        skill = ScrapedSkill(name="s", description="d", content="c", security_verdict="Malicious")
        assert check_security_gate(skill) == "double_warn"

    def test_no_verdict_passes(self):
        skill = ScrapedSkill(name="s", description="d", content="c")
        assert check_security_gate(skill) == "proceed"
