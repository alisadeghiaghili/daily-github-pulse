#!/usr/bin/env python3
"""
forges/github.py — GitHub forge implementation.

Extracts the GitHub-specific API logic from github_repo_of_the_day.py
into a ForgeClient subclass.
"""

from __future__ import annotations

import os
from datetime import date, timedelta, timezone
from typing import Union

import requests

from daily_github_pulse.core.http import get_json, open_session
from daily_github_pulse.core.query import SearchQuery

from .base import ForgeClient, ForgeRepo, ForgeUser, resolve_search_query
from . import register_forge


def _get_headers(token: str | None = None) -> dict:
    """Build HTTP headers for the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@register_forge("github")
class GitHubClient(ForgeClient):
    """GitHub API client implementing the ForgeClient interface.

    Supports the GitHub Search API for repositories and users,
    plus the README endpoint for AI filtering.
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, **kwargs):
        """Initialize the GitHub client.

        Args:
            token: GitHub personal access token. If ``None``, reads from
                   ``GITHUB_TOKEN`` env var.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")

    def _session(self) -> requests.Session:
        """Build a session with GitHub Accept/Auth headers."""
        return open_session(
            self.token,
            extra_headers={"Accept": "application/vnd.github+json"},
            bearer=True,
        )

    def _build_qualifier(
        self,
        keyword: str | None = None,
        keywords: list[str] | None = None,
        keyword_op: str = "AND",
        keyword_not: list[str] | None = None,
        search_in: str = "name,description",
        bool_query: object | None = None,
    ) -> tuple[str, bool]:
        """Build keyword qualifier and determine if in search mode.

        Returns ``(qualifier_string, is_search_mode)``.
        """
        from daily_github_pulse.core.boolean import build_keyword_qualifier

        if bool_query is not None:
            return " " + build_keyword_qualifier(bool_query, search_in=search_in), True

        if keywords is not None:
            if keywords:
                qualifier = " " + build_keyword_qualifier(
                    keywords,
                    keyword_op=keyword_op,
                    keyword_not=keyword_not or [],
                    search_in=search_in,
                )
            else:
                qualifier = ""
            return qualifier, bool(keywords)

        if keyword:
            return f' "{keyword}" in:{search_in}', True
        return "", False

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
        """Search trending repositories on GitHub."""
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
        qualifier, is_search_mode = self._build_qualifier(
            keyword=q.keyword,
            keywords=list(q.keywords) if q.keywords is not None else None,
            keyword_op=q.keyword_op,
            keyword_not=list(q.keyword_not) if q.keyword_not is not None else None,
            search_in=q.search_in,
            bool_query=q.bool_query,
        )

        since_date = q.since_date

        if is_search_mode:
            queries = {
                "New & Relevant": f"created:>={since_date} stars:>50{qualifier}",
                "Active & Relevant": f"pushed:>={since_date} stars:>500{qualifier}",
            }
        else:
            queries = {
                "New Today": f"created:>={since_date} stars:>10",
                "Active Giants": f"pushed:>={since_date} stars:>1000",
            }

        if q.language:
            queries = {k: v + f" language:{q.language}" for k, v in queries.items()}

        results: dict[str, list[ForgeRepo]] = {}
        seen_ids: set = set()
        session = self._session()

        try:
            for label, query_string in queries.items():
                payload = get_json(
                    session,
                    f"{self.BASE_URL}/search/repositories",
                    params={
                        "q": query_string,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": q.top_n,
                    },
                )
                items = payload.get("items", [])

                repos = []
                for r in items:
                    if r["id"] in seen_ids:
                        continue
                    seen_ids.add(r["id"])
                    repos.append(ForgeRepo(
                        forge="github",
                        id=str(r["id"]),
                        full_name=r["full_name"],
                        stars=r.get("stargazers_count", 0),
                        forks=r.get("forks_count", 0),
                        language=r.get("language"),
                        description=r.get("description"),
                        created_at=r.get("created_at", ""),
                        updated_at=r.get("updated_at", ""),
                        url=r.get("html_url", ""),
                    ))
                results[label] = repos
        finally:
            session.close()

        return results

    def search_developers(
        self,
        language: str | None = None,
        since_days: int = 1,
        top_n: int = 10,
    ) -> list[ForgeUser]:
        """Search trending developers on GitHub."""
        since_date = (date.today() - timedelta(days=since_days)).isoformat()
        lang_qualifier = f" language:{language}" if language else ""

        queries = [
            f"created:>={since_date} repos:>0 followers:>0{lang_qualifier}",
            f"followers:>100{lang_qualifier}",
        ]

        seen_logins: set = set()
        raw_users: list[dict] = []

        for query in queries:
            if len(raw_users) >= top_n:
                break
            resp = requests.get(
                f"{self.BASE_URL}/search/users",
                headers=_get_headers(self.token),
                params={"q": query, "sort": "followers", "order": "desc", "per_page": top_n},
                timeout=15,
            )
            resp.raise_for_status()
            for user in resp.json().get("items", []):
                if user["login"] not in seen_logins:
                    seen_logins.add(user["login"])
                    raw_users.append(user)
                if len(raw_users) >= top_n:
                    break

        users: list[ForgeUser] = []
        for user in raw_users[:top_n]:
            try:
                detail_resp = requests.get(
                    f"{self.BASE_URL}/users/{user['login']}",
                    headers=_get_headers(self.token),
                    timeout=15,
                )
                detail_resp.raise_for_status()
                d = detail_resp.json()
            except (requests.RequestException, Exception):
                # Fall back to raw search data
                d = user

            users.append(ForgeUser(
                forge="github",
                login=d.get("login", ""),
                name=d.get("name"),
                company=d.get("company"),
                location=d.get("location"),
                bio=d.get("bio"),
                public_repos=d.get("public_repos", 0),
                followers=d.get("followers", 0),
                following=d.get("following", 0),
                url=d.get("html_url", ""),
            ))

        return users

    def fetch_readme(self, full_name: str, max_chars: int = 800) -> str:
        """Fetch README snippet from GitHub."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/repos/{full_name}/readme",
                headers={**_get_headers(self.token), "Accept": "application/vnd.github.raw+json"},
                timeout=10,
            )
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            return resp.text[:max_chars]
        except (requests.RequestException, UnicodeDecodeError):
            return ""

    def get_token_env_var(self) -> str:
        """Return the env var name for GitHub token."""
        return "GITHUB_TOKEN"
