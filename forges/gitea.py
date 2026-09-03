#!/usr/bin/env python3
"""
forges/gitea.py — Gitea/Codeberg forge implementation.

Implements the ForgeClient interface for Gitea-compatible APIs
(Codeberg, Gitea instances, etc.).
"""

from __future__ import annotations

import os
from datetime import date, timedelta


import requests
import concurrent.futures


from .base import ForgeClient, ForgeRepo, ForgeUser
from . import register_forge


@register_forge("gitea")
class GiteaClient(ForgeClient):
    """Gitea/Codeberg API client implementing the ForgeClient interface.

    Uses the Gitea REST API v1. Supports any Gitea-compatible instance.
    """

    DEFAULT_BASE_URL = "https://gitea.com/api/v1"

    def __init__(self, token: str | None = None, base_url: str | None = None, **kwargs):
        """Initialize the Gitea client.

        Args:
            token:    Gitea API token. If ``None``, reads from
                      ``GITEA_TOKEN`` env var.
            base_url: API base URL. Defaults to gitea.com.
        """
        self.token = token or os.getenv("GITEA_TOKEN")
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def _get_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
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
        """Search trending repositories on Gitea/Codeberg."""
        # Gitea search API
        search_terms = []
        if keyword:
            search_terms.append(keyword)
        elif keywords:
            search_terms.extend(keywords)

        params = {
            "sort": "stars",
            "order": "desc",
            "limit": min(top_n * 2, 50),
        }
        if search_terms:
            params["q"] = " ".join(search_terms)
        if language:
            params["q"] = f"{params.get('q', '')} language:{language}".strip()

        try:
            resp = requests.get(
                f"{self.base_url}/repos/search",
                headers=self._get_headers(),
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            repos_data = data.get("data", []) if isinstance(data, dict) else data
        except requests.RequestException:
            return {}

        # Categorize: new vs active
        since_date = (date.today() - timedelta(days=since_days)).isoformat()
        new_repos = []
        active_repos = []

        for r in repos_data[: top_n * 2]:
            repo = ForgeRepo(
                forge="gitea",
                id=str(r.get("id", "")),
                full_name=r.get("full_name", ""),
                stars=r.get("stargazers_count", 0),
                forks=r.get("forks_count", 0),
                language=r.get("language"),
                description=r.get("description"),
                created_at=r.get("created_at", ""),
                updated_at=r.get("updated_at", ""),
                url=r.get("html_url", ""),
            )

            created = r.get("created_at", "")
            if created >= since_date:
                new_repos.append(repo)
            else:
                active_repos.append(repo)

        results = {}
        if new_repos:
            results["New & Relevant"] = new_repos[:top_n]
        if active_repos:
            results["Active & Relevant"] = active_repos[:top_n]

        # If no categories populated, use a single category
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
        """Search users on Gitea/Codeberg."""
        try:
            resp = requests.get(
                f"{self.base_url}/users/search",
                headers=self._get_headers(),
                params={
                    "sort": "followers_count",
                    "order": "desc",
                    "limit": top_n,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            users_data = data.get("data", []) if isinstance(data, dict) else data
        except requests.RequestException:
            return []

        users = []
        for u in users_data[:top_n]:
            users.append(
                ForgeUser(
                    forge="gitea",
                    login=u.get("login", ""),
                    name=u.get("full_name") or u.get("name"),
                    company=u.get("organization"),
                    location=u.get("location"),
                    bio=u.get("description"),
                    public_repos=u.get("repos_count", 0),
                    followers=u.get("followers_count", 0),
                    following=u.get("following_count", 0),
                    url=u.get("html_url", ""),
                )
            )

        return users

    def fetch_readme(self, full_name: str, max_chars: int = 800) -> str:
        """Fetch README snippet from Gitea/Codeberg."""
        try:
            resp = requests.get(
                f"{self.base_url}/repos/{full_name}/raw/README",
                headers=self._get_headers(),
                timeout=10,
            )
            if resp.status_code == 404:
                # Try common README extensions concurrently
                extensions = ["md", "MD", "rst", "txt"]

                def _fetch_ext(ext):
                    try:
                        r = requests.get(
                            f"{self.base_url}/repos/{full_name}" f"/raw/README.{ext}",
                            headers=self._get_headers(),
                            timeout=10,
                        )
                        if r.status_code == 200:
                            return r
                    except requests.RequestException:
                        pass
                    return None

                # Use a ThreadPoolExecutor but do not use the 'with' context manager
                # because the context manager calls shutdown(wait=True) on exit,
                # which blocks until all running futures finish.
                # We want to return as soon as we find a match and abandon the rest.
                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=len(extensions)
                )

                # Submit all fallback requests in order
                futures = [executor.submit(_fetch_ext, ext) for ext in extensions]

                # Check results in the exact priority order
                for future in futures:
                    res = future.result()
                    if res is not None:
                        resp = res
                        break

                # Shutdown executor without waiting for remaining threads to finish
                executor.shutdown(wait=False)

            if resp.status_code != 200:
                return ""
            return resp.text[:max_chars]
        except (requests.RequestException, UnicodeDecodeError):
            return ""

    def get_token_env_var(self) -> str:
        """Return the env var name for Gitea token."""
        return "GITEA_TOKEN"
