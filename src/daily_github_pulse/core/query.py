"""Shared search request model used by forge clients and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class SearchQuery:
    """
    Normalized parameters for a forge repository search.

    Attributes:
        language:    Programming language filter (e.g. ``"python"``).
        since_days:  Look-back window in days.
        top_n:       Maximum results per category.
        keyword:     Single legacy keyword.
        keywords:    Multi-term boolean keywords.
        keyword_op:  Connector for ``keywords``: ``"AND"`` or ``"OR"``.
        keyword_not: Terms to exclude (list path only).
        search_in:   Comma-separated search scope fields.
        bool_query:  Pre-parsed boolean AST (``Term`` / ``BoolNode``).

    Examples:
        >>> SearchQuery(language="python", top_n=5).language
        'python'
    """

    language: str | None = None
    since_days: int = 1
    top_n: int = 10
    keyword: str | None = None
    keywords: tuple[str, ...] | None = None
    keyword_op: str = "AND"
    keyword_not: tuple[str, ...] | None = None
    search_in: str = "name,description"
    bool_query: Any = None

    def __post_init__(self) -> None:
        if self.keywords is not None:
            object.__setattr__(self, "keywords", tuple(self.keywords))
        if self.keyword_not is not None:
            object.__setattr__(self, "keyword_not", tuple(self.keyword_not))

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> "SearchQuery":
        """
        Build a query from CLI/client kwargs, normalising list inputs.

        Args:
            **kwargs: Same field names as :class:`SearchQuery`.

        Returns:
            A frozen :class:`SearchQuery`.
        """
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in kwargs.items() if k in known}
        return cls(**filtered)

    @property
    def since_date(self) -> str:
        """ISO calendar date for ``today - since_days`` (local timezone)."""
        return (date.today() - timedelta(days=self.since_days)).isoformat()

    def validate(self) -> "SearchQuery":
        """
        Validate mutual exclusion and operator constraints.

        Returns:
            ``self`` when valid (fluent style).

        Raises:
            ValueError: If multiple keyword modes are set or ``keyword_op``
                is not ``AND``/``OR``.
        """
        from daily_github_pulse.core.boolean import VALID_KEYWORD_OPS

        modes = sum(
            [
                self.keyword is not None,
                bool(self.keywords),
                self.bool_query is not None,
            ]
        )
        if modes > 1:
            raise ValueError(
                "'keyword', 'keywords', and 'bool_query' are mutually exclusive."
            )
        if self.keyword_op.strip().upper() not in VALID_KEYWORD_OPS:
            raise ValueError(
                f"Invalid keyword_op '{self.keyword_op}'. "
                f"Valid options: {sorted(VALID_KEYWORD_OPS)}"
            )
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
        if self.since_days < 1:
            raise ValueError("since_days must be >= 1")
        return self

    def with_language(self, language: str | None) -> "SearchQuery":
        """Return a copy with a different language filter."""
        return replace(self, language=language)
