#!/usr/bin/env python3
"""
forges/base.py — Abstract base class and data models for forge API clients.

Provides a unified interface for interacting with different code hosting
platforms (GitHub, GitLab, Gitea, Bitbucket).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True, eq=True)
class ForgeRepo:
    """Normalized repository data across all forges.

    This is the common data model that all forge implementations must produce.
    It decouples the display layer from the specific API shape of each forge.
    """

    forge: str
    """Forge identifier: ``"github"``, ``"gitlab"``, ``"gitea"``, ``"bitbucket"``."""

    id: str
    """Unique identifier within the forge (string to support non-numeric IDs)."""

    full_name: str
    """Owner/name, e.g. ``"owner/repo"``."""

    stars: int
    """Star/watch count."""

    forks: int
    """Fork count."""

    language: str | None
    """Primary programming language, or ``None``."""

    description: str | None
    """Short description, or ``None``."""

    created_at: str
    """ISO-8601 creation timestamp."""

    updated_at: str
    """ISO-8601 last-update timestamp."""

    url: str
    """HTML URL (clickable in terminals that support it)."""


@dataclass(frozen=True, eq=True)
class ForgeUser:
    """Normalized user/developer data across all forges."""

    forge: str
    """Forge identifier."""

    login: str
    """Username / handle."""

    name: str | None
    """Display name, or ``None``."""

    company: str | None
    """Company, or ``None``."""

    location: str | None
    """Location, or ``None``."""

    bio: str | None
    """Short bio, or ``None``."""

    public_repos: int
    """Public repository count."""

    followers: int
    """Follower count."""

    following: int
    """Following count."""

    url: str
    """HTML URL (clickable)."""


# Type alias for AST nodes (from github_repo_of_the_day.py)
# We import these at runtime to avoid circular imports
Term = None  # placeholder, resolved at runtime
BoolNode = None  # placeholder, resolved at runtime


class ForgeClient(ABC):
    """Abstract base class for forge API clients.

    Each forge implementation must subclass this and implement all abstract
    methods. The base class provides no default implementations — each forge
    has its own API quirks that require custom logic.
    """

    @abstractmethod
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
        """Search trending repositories.

        Returns a dict mapping category names (e.g. ``"New Today"``,
        ``"Active Giants"``) to lists of :class:`ForgeRepo`.

        Args:
            language:    Filter by programming language.
            since_days:  Look-back window in days.
            top_n:       Max results per category.
            keyword:     Single keyword filter (legacy).
            keywords:    Multiple keyword terms.
            keyword_op:  Boolean operator for keywords (``"AND"`` or ``"OR"``).
            keyword_not: Terms to exclude.
            search_in:   Comma-separated fields to search.
            bool_query:  Parsed boolean query AST (Term or BoolNode).
        """
        ...

    @abstractmethod
    def search_developers(
        self,
        language: str | None = None,
        since_days: int = 1,
        top_n: int = 10,
    ) -> list[ForgeUser]:
        """Search trending developers.

        Returns a list of :class:`ForgeUser` sorted by relevance/recency.
        """
        ...

    @abstractmethod
    def fetch_readme(self, full_name: str, max_chars: int = 800) -> str:
        """Fetch the first ``max_chars`` characters of a repo's README.

        Used by the AI relevance filter to provide context to the LLM.
        """
        ...

    @abstractmethod
    def get_token_env_var(self) -> str:
        """Return the environment variable name for this forge's auth token."""
        ...
