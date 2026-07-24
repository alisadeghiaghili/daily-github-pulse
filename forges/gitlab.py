#!/usr/bin/env python3
"""
forges/gitlab.py — GitLab forge implementation.

Implements the ForgeClient interface for GitLab's REST API v4.
"""

from __future__ import annotations

import os
from datetime import date, timedelta, timezone

import requests

from .base import ForgeClient, ForgeRepo, ForgeUser
from . import register_forge


@register_forge("gitlab")
class GitLabClient(ForgeClient):
    """GitLab API client implementing the ForgeClient interface.

    Uses the GitLab REST API v4 for project and user search.
    """

    DEFAULT_BASE_URL = "https://gitlab.com/api/v4"

    def __init__(self, token: str | None = None, base_url: str | None = None, **kwargs):
        """Initialize the GitLab client.

        Args:
            token:    GitLab personal access token. If ``None``, reads from
                      ``GITLAB_TOKEN`` env var.
            base_url: API base URL. Defaults to gitlab.com.
        """
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def _get_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def search_repos(
        self,
        language: str | None = None,
        since_days: int = 1,
        top_n: int = 10,
        keyword: str | None = None,
        keywords: list[str] | None = None,
        keyword_op: str = "AND",
        keyword_not: list[str] | None = None,
        search_in: str = "name,description",
        bool_query: object | None = None,
    ) -> dict[str, list[ForgeRepo]]:
        """Search trending projects on GitLab.

        GitLab doesn't have a native "trending" endpoint, so we search
        projects sorted by stars, filtered by recent activity.
        """
        since_date = (date.today() - timedelta(days=since_days)).isoformat()

        # Build search query
        search_terms = []
        if keyword:
            search_terms.append(keyword)
        elif keywords:
            search_terms.extend(keywords)

        search_query = " ".join(search_terms) if search_terms else ""

        # GitLab project search params
        params = {
            "sort": "stars",
            "order_by": "desc",
            "per_page": min(top_n * 2, 100),  # Request more to account for filtering
            "updated_after": f"{since_date}T00:00:00Z",
        }
        if search_query:
            params["search"] = search_query
        if language:
            params["topic"] = language.lower()

        try:
            resp = requests.get(
                f"{self.base_url}/projects",
                headers=self._get_headers(),
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            projects = resp.json()
        except requests.RequestException:
            return {}

        # Categorize results
        new_repos = []
        active_repos = []

        for p in projects[:top_n]:
            repo = ForgeRepo(
                forge="gitlab",
                id=str(p.get("id", "")),
                full_name=p.get("path_with_namespace", ""),
                stars=p.get("star_count", 0),
                forks=p.get("forks_count", 0),
                language=None,  # GitLab API doesn't directly expose language in list
                description=p.get("description"),
                created_at=p.get("created_at", ""),
                updated_at=p.get("last_activity_at", ""),
                url=p.get("web_url", ""),
            )

            # Simple categorization based on creation date
            created = p.get("created_at", "")
            if created >= since_date:
                new_repos.append(repo)
            else:
                active_repos.append(repo)

        results = {}
        if new_repos:
            results["New & Relevant"] = new_repos[:top_n]
        if active_repos:
            results["Active & Relevant"] = active_repos[:top_n]

        return results

    def search_developers(
        self,
        language: str | None = None,
        since_days: int = 1,
        top_n: int = 10,
    ) -> list[ForgeUser]:
        """Search users on GitLab.

        GitLab doesn't have a "trending developers" endpoint, so we
        search for recently active users.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/users",
                headers=self._get_headers(),
                params={
                    "order_by": "created_at",
                    "sort": "desc",
                    "per_page": top_n,
                },
                timeout=15,
            )
            resp.raise_for_status()
            users_data = resp.json()
        except requests.RequestException:
            return []

        users = []
        for u in users_data[:top_n]:
            users.append(ForgeUser(
                forge="gitlab",
                login=u.get("username", ""),
                name=u.get("name"),
                company=u.get("organization"),
                location=u.get("location"),
                bio=u.get("bio"),
                public_repos=u.get("projects_count", 0),
                followers=0,  # GitLab API doesn't expose follower count in list
                following=0,
                url=u.get("web_url", ""),
            ))

        return users

    def fetch_readme(self, full_name: str, max_chars: int = 800) -> str:
        """Fetch README snippet from GitLab."""
        try:
            # GitLab uses URL-encoded project path
            import urllib.parse
            encoded_path = urllib.parse.quote(full_name, safe="")
            resp = requests.get(
                f"{self.base_url}/projects/{encoded_path}/repository/files/README.md/raw",
                headers=self._get_headers(),
                timeout=10,
            )
            if resp.status_code in (404, 400):
                # Try common README variants
                for name in ["readme.md", "Readme.md", "README.rst"]:
                    resp = requests.get(
                        f"{self.base_url}/projects/{encoded_path}/repository/files/{urllib.parse.quote(name, safe='')}/raw",
                        headers=self._get_headers(),
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        break
            if resp.status_code != 200:
                return ""
            return resp.text[:max_chars]
        except (requests.RequestException, UnicodeDecodeError):
            return ""

    def get_token_env_var(self) -> str:
        """Return the env var name for GitLab token."""
        return "GITLAB_TOKEN"
