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
