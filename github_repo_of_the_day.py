#!/usr/bin/env python3
"""
Legacy entry point and public API façade for daily-github-pulse.

Implementation lives in the ``daily_github_pulse`` package. This module
re-exports the historical names so existing scripts and tests keep working,
and retains the GitHub-only search helpers that return raw API dicts.

Prefer::

    python -m daily_github_pulse
    daily-github-pulse
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Union

import requests

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from daily_github_pulse import VERSION  # noqa: E402
from daily_github_pulse.ai.filter import (  # noqa: E402
    AIFilterConfig,
    apply_ai_filter,
    call_anthropic as _call_anthropic,
    call_openai_compatible as _call_openai_compatible,
    fetch_readme_snippet,
    is_repo_relevant,
    load_ai_filter_config,
    repo_identity,
)
from daily_github_pulse.core.boolean import (  # noqa: E402
    VALID_KEYWORD_OPS,
    VALID_SEARCH_IN,
    BoolNode,
    Term,
    _validate_search_in,
    apply_wildcards_to_keywords,
    build_keyword_qualifier,
    expand_wildcards,
    parse_boolean_query,
)
from daily_github_pulse.core.export import (  # noqa: E402
    DEV_EXPORT_FIELDS,
    EXPORT_FIELDS,
    build_dev_export_row,
    build_export_row,
    export_csv,
    export_json,
    write_output,
)
from daily_github_pulse.core.periods import PERIOD_DAYS, resolve_period  # noqa: E402
from daily_github_pulse.core.velocity import (  # noqa: E402
    SNAPSHOT_DIR,
    SNAPSHOT_FILE,
    daily_velocity,
    elapsed_days,
    load_snapshots,
    save_snapshots,
    star_delta,
)
from daily_github_pulse.display.plain import (  # noqa: E402
    format_developer,
    format_repo,
    format_velocity,
)

try:
    from daily_github_pulse.display.rich import (  # noqa: E402
        RICH_AVAILABLE,
        make_ai_filter_progress,
        print_developer_table,
        print_header,
        print_repo_table,
    )
except ImportError:
    RICH_AVAILABLE = False
    print_header = None  # type: ignore[assignment]
    print_repo_table = None  # type: ignore[assignment]
    print_developer_table = None  # type: ignore[assignment]
    make_ai_filter_progress = None  # type: ignore[assignment]

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")


def get_headers() -> dict:
    """Build HTTP headers for the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def search_trending_repos(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    keyword_not: list[str] | None = None,
    search_in: str = "name,description",
    bool_query: Union[Term, BoolNode, None] = None,
) -> dict:
    """
    Query the GitHub Search API and return top repositories by category.

    Args:
        language:    Language filter (e.g. ``"python"``).
        since_days:  Days to look back.
        top_n:       Max results per category.
        keyword:     Single keyword string (legacy).
        keywords:    List of keyword terms for boolean search.
        keyword_op:  Connector for ``keywords``: ``"AND"`` or ``"OR"``.
        keyword_not: Exclusion terms for ``keywords`` path.
        search_in:   Comma-separated search scope.
        bool_query:  Pre-parsed AST from ``parse_boolean_query()``.

    Returns:
        Mapping of category label to list of raw GitHub repo dicts.

    Raises:
        ValueError: If more than one keyword input mode is active.
    """
    active_modes = sum(
        [
            keyword is not None,
            bool(keywords),
            bool_query is not None,
        ]
    )
    if active_modes > 1:
        raise ValueError(
            "'keyword', 'keywords', and 'bool_query' are mutually exclusive."
        )

    _validate_search_in(search_in)
    since_date = (date.today() - timedelta(days=since_days)).isoformat()

    if bool_query is not None:
        keyword_qualifier = " " + build_keyword_qualifier(
            bool_query, search_in=search_in
        )
        is_search_mode = True
    elif keywords is not None:
        keyword_qualifier = (
            " "
            + build_keyword_qualifier(
                keywords,
                keyword_op=keyword_op,
                keyword_not=keyword_not or [],
                search_in=search_in,
            )
            if keywords
            else ""
        )
        is_search_mode = bool(keywords)
    else:
        keyword_qualifier = f' "{keyword}" in:{search_in}' if keyword else ""
        is_search_mode = bool(keyword)

    if is_search_mode:
        queries = {
            "New & Relevant": f"created:>={since_date} stars:>50{keyword_qualifier}",
            "Active & Relevant": f"pushed:>={since_date} stars:>500{keyword_qualifier}",
        }
    else:
        queries = {
            "New Today": f"created:>={since_date} stars:>10",
            "Active Giants": f"pushed:>={since_date} stars:>1000",
        }

    if language:
        queries = {k: v + f" language:{language}" for k, v in queries.items()}

    results: dict = {}
    seen_ids: set = set()

    for label, query in queries.items():
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=get_headers(),
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": top_n,
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        unique = [r for r in items if r["id"] not in seen_ids]
        seen_ids.update(r["id"] for r in unique)
        results[label] = unique

    return results


def search_trending_developers(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
) -> list[dict]:
    """
    Query the GitHub Search API and return top active developers.

    Args:
        language:   Optional language qualifier.
        since_days: Look-back window in days.
        top_n:      Max developers to return.

    Returns:
        List of enriched GitHub user dicts.
    """
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
            "https://api.github.com/search/users",
            headers=get_headers(),
            params={
                "q": query,
                "sort": "followers",
                "order": "desc",
                "per_page": top_n,
            },
            timeout=15,
        )
        resp.raise_for_status()
        for user in resp.json().get("items", []):
            if user["login"] not in seen_logins:
                seen_logins.add(user["login"])
                raw_users.append(user)
            if len(raw_users) >= top_n:
                break

    enriched: list[dict] = []
    for user in raw_users[:top_n]:
        try:
            detail_resp = requests.get(
                f"https://api.github.com/users/{user['login']}",
                headers=get_headers(),
                timeout=15,
            )
            detail_resp.raise_for_status()
            enriched.append(detail_resp.json())
        except requests.RequestException:
            enriched.append(user)

    return enriched


def _build_arg_parser():
    """Build the legacy GitHub-only CLI parser."""
    import argparse

    from daily_github_pulse.cli import _build_arg_parser as _pulse_parser

    # Reuse the multi-forge parser surface for the legacy entry as well.
    return _pulse_parser()


def main() -> None:
    """Run the multi-forge CLI (shared implementation)."""
    global GITHUB_TOKEN  # noqa: PLW0603

    parser = _build_arg_parser()
    args = parser.parse_args()
    if args.token:
        GITHUB_TOKEN = args.token
        os.environ["GITHUB_TOKEN"] = args.token

    from daily_github_pulse.cli import main as pulse_main

    pulse_main()


if __name__ == "__main__":
    main()
