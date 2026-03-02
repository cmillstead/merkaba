# tests/test_plugin_forge.py
import pytest

try:
    from merkaba.plugins.forge import classify_url, UrlKind
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    classify_url = None
    UrlKind = None

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
