# tests/test_github_adapter.py
import sys
from unittest.mock import MagicMock, patch

import pytest

try:
    import keyring.errors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing keyring")

from merkaba.integrations.github_adapter import GitHubAdapter
from merkaba.integrations.base import ADAPTER_REGISTRY


def test_github_adapter_registered():
    assert "github" in ADAPTER_REGISTRY


# --- Fixtures ---


@pytest.fixture
def mock_keyring(mocker):
    """Provide keyring with a valid personal_access_token."""
    stored = {
        ("merkaba-ai", "integration:github:personal_access_token"): "ghp_test123",
    }
    mocker.patch(
        "merkaba.security.secrets.keyring.get_password",
        side_effect=lambda svc, key: stored.get((svc, key)),
    )
    return stored


@pytest.fixture
def mock_github_module():
    """Create a mock github module with a mock Github class."""
    mock_mod = MagicMock()
    mock_gh_instance = MagicMock()
    mock_mod.Github.return_value = mock_gh_instance
    return mock_mod, mock_gh_instance


@pytest.fixture
def github_adapter(mock_keyring, mock_github_module, mocker):
    """A connected GitHubAdapter with mocked PyGithub."""
    mock_mod, mock_gh_instance = mock_github_module
    mocker.patch.dict(sys.modules, {"github": mock_mod})

    adapter = GitHubAdapter(name="github")
    adapter.connect()
    return adapter


# --- Connect tests ---


def test_connect_fails_without_credentials(mocker):
    mocker.patch("merkaba.security.secrets.keyring.get_password", return_value=None)
    adapter = GitHubAdapter(name="github")
    result = adapter.connect()
    assert result is False
    assert adapter.is_connected is False


def test_connect_succeeds(mock_keyring, mock_github_module, mocker):
    mock_mod, mock_gh_instance = mock_github_module
    mocker.patch.dict(sys.modules, {"github": mock_mod})

    adapter = GitHubAdapter(name="github")
    result = adapter.connect()
    assert result is True
    assert adapter.is_connected is True
    mock_mod.Github.assert_called_once_with("ghp_test123")


# --- Action tests ---


def test_list_repos(github_adapter):
    mock_repo = MagicMock()
    mock_repo.name = "merkaba"
    mock_repo.full_name = "cevin/merkaba"
    mock_repo.description = "Personal assistant"
    mock_repo.html_url = "https://github.com/cevin/merkaba"
    mock_repo.stargazers_count = 42

    mock_user = MagicMock()
    mock_user.get_repos.return_value = [mock_repo]
    github_adapter._gh.get_user.return_value = mock_user

    result = github_adapter.execute("list_repos")
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["repos"][0]["name"] == "merkaba"
    assert result["repos"][0]["full_name"] == "cevin/merkaba"
    assert result["repos"][0]["stars"] == 42


def test_list_issues(github_adapter):
    mock_issue = MagicMock()
    mock_issue.number = 1
    mock_issue.title = "Bug report"
    mock_issue.state = "open"
    mock_issue.user.login = "cevin"
    mock_issue.html_url = "https://github.com/cevin/merkaba/issues/1"

    mock_repo = MagicMock()
    mock_repo.get_issues.return_value = [mock_issue]
    github_adapter._gh.get_repo.return_value = mock_repo

    result = github_adapter.execute("list_issues", {"repo": "cevin/merkaba"})
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["issues"][0]["number"] == 1
    assert result["issues"][0]["title"] == "Bug report"
    mock_repo.get_issues.assert_called_once_with(state="open")


def test_create_issue(github_adapter):
    mock_issue = MagicMock()
    mock_issue.number = 42
    mock_issue.html_url = "https://github.com/cevin/merkaba/issues/42"
    mock_issue.title = "New feature"

    mock_repo = MagicMock()
    mock_repo.create_issue.return_value = mock_issue
    github_adapter._gh.get_repo.return_value = mock_repo

    result = github_adapter.execute("create_issue", {
        "repo": "cevin/merkaba",
        "title": "New feature",
        "body": "Please add this feature",
    })
    assert result["ok"] is True
    assert result["number"] == 42
    assert result["url"] == "https://github.com/cevin/merkaba/issues/42"
    mock_repo.create_issue.assert_called_once_with(
        title="New feature", body="Please add this feature"
    )


def test_list_prs(github_adapter):
    mock_pr = MagicMock()
    mock_pr.number = 10
    mock_pr.title = "Add GitHub adapter"
    mock_pr.state = "open"
    mock_pr.user.login = "cevin"
    mock_pr.html_url = "https://github.com/cevin/merkaba/pull/10"

    mock_repo = MagicMock()
    mock_repo.get_pulls.return_value = [mock_pr]
    github_adapter._gh.get_repo.return_value = mock_repo

    result = github_adapter.execute("list_prs", {"repo": "cevin/merkaba"})
    assert result["ok"] is True
    assert result["count"] == 1
    assert result["prs"][0]["number"] == 10
    assert result["prs"][0]["title"] == "Add GitHub adapter"
    mock_repo.get_pulls.assert_called_once_with(state="open")


def test_get_pr(github_adapter):
    mock_pr = MagicMock()
    mock_pr.number = 10
    mock_pr.title = "Add GitHub adapter"
    mock_pr.state = "open"
    mock_pr.user.login = "cevin"
    mock_pr.html_url = "https://github.com/cevin/merkaba/pull/10"
    mock_pr.body = "This PR adds the GitHub integration adapter."
    mock_pr.mergeable = True

    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    github_adapter._gh.get_repo.return_value = mock_repo

    result = github_adapter.execute("get_pr", {"repo": "cevin/merkaba", "number": 10})
    assert result["ok"] is True
    assert result["number"] == 10
    assert result["title"] == "Add GitHub adapter"
    assert result["mergeable"] is True
    assert result["body"] == "This PR adds the GitHub integration adapter."
    mock_repo.get_pull.assert_called_once_with(10)


def test_add_comment(github_adapter):
    mock_comment = MagicMock()
    mock_comment.id = 999
    mock_comment.html_url = "https://github.com/cevin/merkaba/issues/1#issuecomment-999"

    mock_issue = MagicMock()
    mock_issue.create_comment.return_value = mock_comment

    mock_repo = MagicMock()
    mock_repo.get_issue.return_value = mock_issue
    github_adapter._gh.get_repo.return_value = mock_repo

    result = github_adapter.execute("add_comment", {
        "repo": "cevin/merkaba",
        "issue_number": 1,
        "body": "Looks good!",
    })
    assert result["ok"] is True
    assert result["comment_id"] == 999
    mock_issue.create_comment.assert_called_once_with("Looks good!")


def test_unknown_action(github_adapter):
    result = github_adapter.execute("unknown_action")
    assert result["ok"] is False
    assert "Unknown action" in result["error"]


# --- Health check tests ---


def test_health_check_not_connected():
    adapter = GitHubAdapter(name="github")
    result = adapter.health_check()
    assert result["ok"] is False
    assert result["adapter"] == "github"


def test_health_check_connected(github_adapter):
    mock_user = MagicMock()
    mock_user.login = "cevin"
    github_adapter._gh.get_user.return_value = mock_user

    result = github_adapter.health_check()
    assert result["ok"] is True
    assert result["adapter"] == "github"
    assert result["user"] == "cevin"


# --- Error path tests ---


def test_list_repos_error(github_adapter):
    github_adapter._gh.get_user.side_effect = Exception("API rate limit exceeded")

    result = github_adapter.execute("list_repos")
    assert result["ok"] is False
    assert "API rate limit exceeded" in result["error"]
    assert result["repos"] == []
