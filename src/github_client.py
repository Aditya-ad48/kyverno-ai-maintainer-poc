"""Lightweight, read-only GitHub API client for kyverno/kyverno."""

import httpx
import time
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from typing import Any
from dotenv import load_dotenv

load_dotenv()

@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    created_at: str
    url: str

@dataclass
class PRFile:
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int

@dataclass
class PullRequest:
    number: int
    title: str
    state: str
    merged: bool
    changed_files: list[PRFile]
    labels: list[str]
    url: str


class KyvernoGitHubClient:
    """Read-only GitHub API client scoped to kyverno/kyverno."""
    
    BASE = "https://api.github.com/repos/kyverno/kyverno"
    
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = httpx.Client(headers=headers, timeout=30.0)
        self._cache_dir = Path("data/cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        """Make a GET request with basic rate-limit awareness."""
        url = f"{self.BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
        resp = self.client.get(url, params=params)
        
        # Handle rate limiting
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining", "unknown")
            reset_time = resp.headers.get("X-RateLimit-Reset", "")
            raise RuntimeError(
                f"GitHub API rate limit hit. Remaining: {remaining}. "
                f"Resets at: {reset_time}"
            )
        
        resp.raise_for_status()
        return resp.json()
    
    def get_issue(self, number: int) -> GitHubIssue:
        """Fetch a single issue by number."""
        data = self._get(f"issues/{number}")
        return GitHubIssue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", "") or "",
            labels=[l["name"] for l in data.get("labels", [])],
            state=data["state"],
            created_at=data["created_at"],
            url=data["html_url"],
        )
    
    def get_closed_issues(self, count: int = 50, labels: str | None = None) -> list[GitHubIssue]:
        """Fetch recent closed issues. Only fetches actual issues, not PRs."""
        issues = []
        page = 1
        per_page = min(count, 100)
        
        while len(issues) < count:
            params = {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            }
            if labels:
                params["labels"] = labels
            
            data = self._get("issues", params=params)
            if not data:
                break
            
            for item in data:
                # Skip pull requests (GitHub API returns PRs in issues endpoint)
                if "pull_request" in item:
                    continue
                issues.append(GitHubIssue(
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body", "") or "",
                    labels=[l["name"] for l in item.get("labels", [])],
                    state=item["state"],
                    created_at=item["created_at"],
                    url=item["html_url"],
                ))
                if len(issues) >= count:
                    break
            page += 1
        
        return issues[:count]
    
    def get_pr_files(self, pr_number: int) -> list[PRFile]:
        """Fetch the list of changed files in a PR."""
        data = self._get(f"pulls/{pr_number}/files", params={"per_page": 100})
        return [
            PRFile(
                filename=f["filename"],
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
            )
            for f in data
        ]
    
    def get_merged_prs(self, count: int = 20) -> list[PullRequest]:
        """Fetch recent merged PRs."""
        prs = []
        page = 1
        
        while len(prs) < count:
            params = {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
            data = self._get("pulls", params=params)
            if not data:
                break
            
            for item in data:
                if item.get("merged_at") is not None:
                    prs.append(PullRequest(
                        number=item["number"],
                        title=item["title"],
                        state=item["state"],
                        merged=True,
                        changed_files=[],  # filled lazily
                        labels=[l["name"] for l in item.get("labels", [])],
                        url=item["html_url"],
                    ))
                    if len(prs) >= count:
                        break
            page += 1
        
        return prs[:count]
    
    def get_repo_tree(self, path: str = "") -> list[dict]:
        """Fetch the directory tree at a given path."""
        data = self._get(f"contents/{path}")
        return data if isinstance(data, list) else [data]
    
    def get_labels(self) -> list[str]:
        """Fetch all repository labels."""
        labels = []
        page = 1
        while True:
            data = self._get("labels", params={"per_page": 100, "page": page})
            if not data:
                break
            labels.extend([l["name"] for l in data])
            page += 1
        return labels
    
    def save_cache(self, key: str, data: Any):
        """Cache API responses to disk."""
        cache_file = self._cache_dir / f"{key}.json"
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_cache(self, key: str) -> Any | None:
        """Load cached API response."""
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None
