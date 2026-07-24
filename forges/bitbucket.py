#!/usr/bin/env python3
"""
forges/bitbucket.py — Bitbucket forge implementation.

Implements the ForgeClient interface for Bitbucket REST API v2.0.
"""

from __future__ import annotations

import os
from datetime import date, timedelta, timezone

import requests

from .base import ForgeClient, ForgeRepo, ForgeUser
from . import register_forge


@register_forge("bitbucket")
class BitbucketClient(ForgeClient):
    """Bitbucket API client implementing the ForgeClient interface.

    Uses the Bitbucket REST API v2.0 for repository and user search.
    """

    BASE_URL = "https://api.bitbucket.org/2.0"

    def __init__(
        self,
        token: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        **kwargs,
    ):
        """Initialize the Bitbucket client.

        Args:
            token:       Bitbucket app password (used as basic auth).
            username:    Bitbucket username (for basic auth).
            app_password: Bitbucket app password (for basic auth).
        """
        self.username = username or os.getenv("BITBUCKET_USER")
        self.app_password = app_password or os.getenv("BITBUCKET_APP_PASSWORD")

    def _get_auth(self) -> tuple[str, str] | None:
        """Return (username, app_password) for basic auth, or None."""
        if self.username and self.app_password:
            return (self.username, self.app_password)
        return None

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
        """Search repositories on Bitbucket.

        Bitbucket doesn't have a "trending" endpoint, so we search
        repositories sorted by stars (watchers) with date filtering.
        """
        since_date = (date.today() - timedelta(days=since_days)).isoformat()

        # Build search query
        search_terms = []
        if keyword:
            search_terms.append(keyword)
        elif keywords:
            search_terms.extend(keywords)

        # Bitbucket uses workspace/repo structure
        # We search across all public repos
        params = {
            "sort": "-stargazers_count",
            "pagelen": min(top_n * 2, 50),
        }

        if search_terms:
            params["q"] = " ".join(search_terms)

        try:
            auth = self._get_auth()
            resp = requests.get(
                f"{self.BASE_URL}/repositories",
                auth=auth,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            repos_data = data.get("values", [])
        except requests.RequestException:
            return {}

        # Categorize results
        new_repos = []
        active_repos = []

        for r in repos_data[:top_n * 2]:
            # Extract language from languages link if available
            lang = None
            if "language" in r:
                lang = r["language"]

            repo = ForgeRepo(
                forge="bitbucket",
                id=r.get("uuid", ""),
                full_name=r.get("full_name", ""),
                stars=r.get("stargazers_count", 0),
                forks=r.get("forks_count", 0),
                language=lang,
                description=r.get("description"),
                created_at=r.get("created_on", ""),
                updated_at=r.get("updated_on", ""),
                url=r.get("links", {}).get("html", {}).get("href", ""),
            )

            created = r.get("created_on", "")
            if created >= since_date:
                new_repos.append(repo)
            else:
                active_repos.append(repo)

        results = {}
        if new_repos:
            results["New & Relevant"] = new_repos[:top_n]
        if active_repos:
            results["Active & Relevant"] = active_repos[:top_n]

        if not results:
            all_repos = new_repos + active_repos
            if all_repos:
                results["Trending Repositories"] = all_repos[:top_n]

        return results

    def search_developers(
        self,
        language: str | None = None,
        since_days: int = 1,
        top_n: int = 10,
    ) -> list[ForgeUser]:
        """Search users on Bitbucket.

        Bitbucket doesn't have a user search endpoint like GitHub,
        so this returns an empty list for now.
        """
        # Bitbucket API v2 doesn't have a public user search endpoint
        return []

    def fetch_readme(self, full_name: str, max_chars: int = 800) -> str:
        """Fetch README snippet from Bitbucket."""
        try:
            # Try common README filenames
            for name in ["README.md", "README.rst", "README.txt", "README"]:
                resp = requests.get(
                    f"{self.BASE_URL}/repositories/{full_name}/src/master/{name}",
                    auth=self._get_auth(),
                    timeout=10,
                )
                if resp.status_code == 200:
                    return resp.text[:max_chars]
            return ""
        except (requests.RequestException, UnicodeDecodeError):
            return ""

    def get_token_env_var(self) -> str:
        """Return the env var name for Bitbucket token."""
        return "BITBUCKET_USER"
