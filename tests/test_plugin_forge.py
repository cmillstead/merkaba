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

try:
    from merkaba.plugins.forge import build_generation_prompt, generate_plugin
except ImportError:
    build_generation_prompt = None
    generate_plugin = None

try:
    from merkaba.plugins.forge import scan_and_write, ForgeResult
except ImportError:
    scan_and_write = None
    ForgeResult = None

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


class TestBuildGenerationPrompt:
    def test_includes_skill_description(self):
        skill = ScrapedSkill(name="test", description="Automates code reviews", content="...")
        prompt = build_generation_prompt(skill)
        assert "Automates code reviews" in prompt

    def test_includes_merkaba_tools(self):
        skill = ScrapedSkill(name="test", description="Does stuff", content="...")
        prompt = build_generation_prompt(skill)
        assert "file_read" in prompt
        assert "memory_search" in prompt

    def test_includes_skill_md_format(self):
        skill = ScrapedSkill(name="test", description="Does stuff", content="...")
        prompt = build_generation_prompt(skill)
        assert "SKILL.md" in prompt
        assert "frontmatter" in prompt.lower()

    def test_includes_no_code_instruction(self):
        skill = ScrapedSkill(name="test", description="Does stuff", content="...")
        prompt = build_generation_prompt(skill)
        assert "NOT reproduce" in prompt or "not reproduce" in prompt.lower()

    def test_includes_security_context_when_available(self):
        skill = ScrapedSkill(
            name="test", description="Does stuff", content="...",
            security_verdict="Suspicious",
            security_analysis="Uses dynamic execution patterns"
        )
        prompt = build_generation_prompt(skill)
        assert "Suspicious" in prompt
        assert "dynamic execution" in prompt


class TestGeneratePlugin:
    def test_calls_llm_with_prompt(self):
        from merkaba.llm import LLMResponse

        skill = ScrapedSkill(name="review-helper", description="Helps review code", content="...")

        mock_llm = MagicMock()
        mock_llm.chat_with_fallback.return_value = LLMResponse(
            content="---\nname: review-helper\ndescription: Helps review code\n---\n# Review Helper\n\nCheck files for issues using file_read.\n",
            model="test"
        )

        with patch("merkaba.llm.LLMClient", return_value=mock_llm):
            result = generate_plugin(skill)

        mock_llm.chat_with_fallback.assert_called_once()
        assert "review-helper" in result["skill_md"]

    def test_returns_structured_output(self):
        from merkaba.llm import LLMResponse

        skill = ScrapedSkill(name="test", description="d", content="c")
        llm_output = "---\nname: test\ndescription: d\n---\n# Test\nContent"

        mock_llm = MagicMock()
        mock_llm.chat_with_fallback.return_value = LLMResponse(content=llm_output, model="test")

        with patch("merkaba.llm.LLMClient", return_value=mock_llm):
            result = generate_plugin(skill)

        assert "skill_md" in result
        assert isinstance(result["skill_md"], str)

    def test_none_response_raises(self):
        from merkaba.llm import LLMResponse

        skill = ScrapedSkill(name="test", description="d", content="c")

        mock_llm = MagicMock()
        mock_llm.chat_with_fallback.return_value = LLMResponse(content=None, model="test")

        with patch("merkaba.llm.LLMClient", return_value=mock_llm):
            with pytest.raises(RuntimeError, match="LLM"):
                generate_plugin(skill)


class TestScanAndWrite:
    def test_clean_skill_writes_to_disk(self, tmp_path):
        content = {
            "skill_md": "---\nname: test\ndescription: d\n---\n# Test\nUse file_read."
        }
        result = scan_and_write("test-plugin", content, str(tmp_path))

        assert result.success is True
        assert result.warnings == []
        skill_path = tmp_path / "test-plugin" / "skills" / "test-plugin" / "SKILL.md"
        assert skill_path.exists()
        assert "file_read" in skill_path.read_text()

    def test_flagged_skill_returns_warnings(self, tmp_path):
        # Use "subprocess" which is in DANGEROUS_SKILL_PATTERNS
        content = {
            "skill_md": "---\nname: test\ndescription: d\n---\n# Test\nRun subprocess.call()"
        }
        result = scan_and_write("test-plugin", content, str(tmp_path), confirm=False)

        assert result.success is False
        assert len(result.warnings) > 0
        skill_path = tmp_path / "test-plugin" / "skills" / "test-plugin" / "SKILL.md"
        assert not skill_path.exists()

    def test_flagged_skill_writes_when_confirmed(self, tmp_path):
        content = {
            "skill_md": "---\nname: test\ndescription: d\n---\n# Test\nRun subprocess.call()"
        }
        result = scan_and_write("test-plugin", content, str(tmp_path), confirm=True)

        assert result.success is True
        assert len(result.warnings) > 0
        skill_path = tmp_path / "test-plugin" / "skills" / "test-plugin" / "SKILL.md"
        assert skill_path.exists()

    def test_custom_name_used_for_directory(self, tmp_path):
        content = {
            "skill_md": "---\nname: original\ndescription: d\n---\n# Test\nContent"
        }
        result = scan_and_write("custom-name", content, str(tmp_path))

        assert result.success is True
        skill_path = tmp_path / "custom-name" / "skills" / "custom-name" / "SKILL.md"
        assert skill_path.exists()

    def test_adds_forged_from_metadata(self, tmp_path):
        content = {
            "skill_md": "---\nname: test\ndescription: d\n---\n# Test\nContent"
        }
        result = scan_and_write("test", content, str(tmp_path), source_url="https://clawhub.ai/skills/x")

        skill_path = tmp_path / "test" / "skills" / "test" / "SKILL.md"
        written = skill_path.read_text()
        assert "forged_from" in written
        assert "clawhub.ai" in written
