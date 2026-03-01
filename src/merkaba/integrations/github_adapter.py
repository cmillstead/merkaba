# src/friday/integrations/github_adapter.py
"""GitHub integration adapter — repos, issues, PRs, comments via PyGithub."""

import logging
from dataclasses import dataclass, field
from typing import Any

from friday.integrations.base import IntegrationAdapter, register_adapter
from friday.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = [
    "personal_access_token",
]


@dataclass
class GitHubAdapter(IntegrationAdapter):
    """GitHub adapter: repos, issues, PRs, and comments via PyGithub."""

    _creds: CredentialManager = field(default_factory=CredentialManager, init=False, repr=False)
    _gh: Any = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        ok, missing = self._creds.has_required("github", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("GitHub adapter missing credentials: %s", missing)
            self._connected = False
            return False

        token = self._creds.get("github", "personal_access_token")
        try:
            from github import Github
            self._gh = Github(token)
            self._connected = True
            return True
        except Exception as e:
            logger.error("GitHub connect failed: %s", e)
            self._connected = False
            return False

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        if action == "list_repos":
            return self._list_repos(params)
        elif action == "list_issues":
            return self._list_issues(params)
        elif action == "create_issue":
            return self._create_issue(params)
        elif action == "list_prs":
            return self._list_prs(params)
        elif action == "get_pr":
            return self._get_pr(params)
        elif action == "add_comment":
            return self._add_comment(params)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    def health_check(self) -> dict:
        if not self._connected or self._gh is None:
            return {"ok": False, "adapter": "github"}
        try:
            login = self._gh.get_user().login
            return {"ok": True, "adapter": "github", "user": login}
        except Exception as e:
            logger.error("GitHub health check failed: %s", e)
            return {"ok": False, "adapter": "github", "error": str(e)}

    def _list_repos(self, params: dict) -> dict:
        limit = params.get("limit", 30)
        try:
            user = self._gh.get_user()
            repos = []
            for repo in user.get_repos()[:limit]:
                repos.append({
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "url": repo.html_url,
                    "stars": repo.stargazers_count,
                })
            return {"ok": True, "repos": repos, "count": len(repos)}
        except Exception as e:
            logger.error("GitHub list_repos failed: %s", e)
            return {"ok": False, "error": str(e), "repos": []}

    def _list_issues(self, params: dict) -> dict:
        repo_name = params.get("repo")
        if not repo_name:
            return {"ok": False, "error": "Missing required param: repo"}
        state = params.get("state", "open")
        try:
            repo = self._gh.get_repo(repo_name)
            issues = []
            for issue in repo.get_issues(state=state):
                issues.append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "user": issue.user.login,
                    "url": issue.html_url,
                })
            return {"ok": True, "issues": issues, "count": len(issues)}
        except Exception as e:
            logger.error("GitHub list_issues failed: %s", e)
            return {"ok": False, "error": str(e), "issues": []}

    def _create_issue(self, params: dict) -> dict:
        required = {"repo", "title", "body"}
        if not required.issubset(params.keys()):
            missing = required - params.keys()
            return {"ok": False, "error": f"Missing required params: {missing}"}
        try:
            repo = self._gh.get_repo(params["repo"])
            issue = repo.create_issue(title=params["title"], body=params["body"])
            return {
                "ok": True,
                "number": issue.number,
                "url": issue.html_url,
                "title": issue.title,
            }
        except Exception as e:
            logger.error("GitHub create_issue failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _list_prs(self, params: dict) -> dict:
        repo_name = params.get("repo")
        if not repo_name:
            return {"ok": False, "error": "Missing required param: repo"}
        state = params.get("state", "open")
        try:
            repo = self._gh.get_repo(repo_name)
            prs = []
            for pr in repo.get_pulls(state=state):
                prs.append({
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "user": pr.user.login,
                    "url": pr.html_url,
                })
            return {"ok": True, "prs": prs, "count": len(prs)}
        except Exception as e:
            logger.error("GitHub list_prs failed: %s", e)
            return {"ok": False, "error": str(e), "prs": []}

    def _get_pr(self, params: dict) -> dict:
        repo_name = params.get("repo")
        number = params.get("number")
        if not repo_name or number is None:
            return {"ok": False, "error": "Missing required params: repo, number"}
        try:
            repo = self._gh.get_repo(repo_name)
            pr = repo.get_pull(int(number))
            return {
                "ok": True,
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "user": pr.user.login,
                "url": pr.html_url,
                "body": pr.body,
                "mergeable": pr.mergeable,
            }
        except Exception as e:
            logger.error("GitHub get_pr failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _add_comment(self, params: dict) -> dict:
        required = {"repo", "issue_number", "body"}
        if not required.issubset(params.keys()):
            missing = required - params.keys()
            return {"ok": False, "error": f"Missing required params: {missing}"}
        try:
            repo = self._gh.get_repo(params["repo"])
            issue = repo.get_issue(int(params["issue_number"]))
            comment = issue.create_comment(params["body"])
            return {"ok": True, "comment_id": comment.id, "url": comment.html_url}
        except Exception as e:
            logger.error("GitHub add_comment failed: %s", e)
            return {"ok": False, "error": str(e)}


register_adapter("github", GitHubAdapter)
