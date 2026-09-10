#!/usr/bin/env python3
"""
forges/bitbucket.py — Bitbucket forge implementation.

Implements the ForgeClient interface for Bitbucket REST API v2.0.
"""

from __future__ import annotations

import os
from datetime import date, timedelta, timezone

import requests

from daily_github_pulse.core.http import RateLimitError, get_json, open_session
from daily_github_pulse.core.query import SearchQuery

from .base import ForgeClient, ForgeRepo, ForgeUser, resolve_search_query
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

    def _session(self) -> requests.Session:
        session = open_session(None, bearer=False)
        auth = self._get_auth()
        if auth:
            session.auth = auth
        return session

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
        query: SearchQuery | None = None,
    ) -> dict[str, list[ForgeRepo]]:
        """Search repositories on Bitbucket.

        Bitbucket doesn't have a "trending" endpoint, so we search
        repositories sorted by stars (watchers) with date filtering.
        """
        q = resolve_search_query(
            query,
            language=language,
            since_days=since_days,
            top_n=top_n,
            keyword=keyword,
            keywords=keywords,
            keyword_op=keyword_op,
            keyword_not=keyword_not,
            search_in=search_in,
            bool_query=bool_query,
        )
        since_date = q.since_date

        search_terms = []
        if q.keyword:
            search_terms.append(q.keyword)
        elif q.keywords:
            search_terms.extend(q.keywords)

        params = {
            "sort": "-stargazers_count",
            "pagelen": min(q.top_n * 2, 50),
        }

        if search_terms:
            params["q"] = " ".join(search_terms)

        session = self._session()
        try:
            data = get_json(session, f"{self.BASE_URL}/repositories", params=params)
            repos_data = data.get("values", []) if isinstance(data, dict) else []
        except RateLimitError:
            raise
        except Exception:
            return {}
        finally:
            session.close()

        # Categorize results
        new_repos = []
        active_repos = []

        for r in repos_data[: q.top_n * 2]:
            lang = r.get("language")

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
            results["New & Relevant"] = new_repos[: q.top_n]
        if active_repos:
            results["Active & Relevant"] = active_repos[: q.top_n]

        if not results:
            all_repos = new_repos + active_repos
            if all_repos:
                results["Trending Repositories"] = all_repos[: q.top_n]

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
