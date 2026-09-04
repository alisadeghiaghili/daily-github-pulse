#!/usr/bin/env python3
"""
daily-github-pulse  v3.0.0
Discover trending repositories and developers across all major forges —
GitHub, GitLab, Gitea/Codeberg, and Bitbucket —
with real star velocity, boolean keyword search, wildcard expansion,
and AI relevance filtering.
──────────────────────────────────────────────────────────────────────
Run it once. See what's blowing up on code hosting platforms right now.

  python daily_github_pulse.py                              # today's hottest repos (GitHub)
  python daily_github_pulse.py --forge gitlab               # trending on GitLab
  python daily_github_pulse.py --forge gitea --gitea-url https://codeberg.org
  python daily_github_pulse.py --forge github,gitlab        # merged from both

What you get
────────────
A ranked list of repositories (or developers) pulled live from the API,
sorted by stars.  Run it again tomorrow and it also shows you how many stars
each repo gained since your last run — so you see momentum, not just totals.

  ======================================================================
  #1  [GitHub] openai/openai-python
      Stars: 24,312  Forks: 3,201  Lang: Python
    Δ +418 ⭐ total  |  ~418.0 ⭐/day
      Created: 2022-11-01  |  Updated: 2026-06-03
      The official Python library for the OpenAI API
      https://github.com/openai/openai-python

Token setup (optional — raises rate limit from 60 to 5,000 req/hr)
───────────────────────────────────────────────────────────────────
  cp .env.example .env   # then set tokens for your chosen forges
  Get a token: https://github.com/settings/tokens
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Union

# ──────────────────────────────────────────────
# Optional dependency loading
# ──────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ──────────────────────────────────────────────
# Rich display — optional, graceful fallback
# ──────────────────────────────────────────────
try:
    from rich_display import (
        print_header,
        print_repo_table,
        print_developer_table,
        RICH_AVAILABLE,
    )
except ImportError:
    RICH_AVAILABLE = False
    print_header = None
    print_repo_table = None
    print_developer_table = None

# ──────────────────────────────────────────────
# Import from legacy module for shared utilities
# ──────────────────────────────────────────────
try:
    from github_repo_of_the_day import (
        VERSION as _LEGACY_VERSION,
        PERIOD_DAYS,
        VALID_SEARCH_IN,
        VALID_KEYWORD_OPS,
        EXPORT_FIELDS,
        DEV_EXPORT_FIELDS,
        SNAPSHOT_DIR,
        SNAPSHOT_FILE,
        Term,
        BoolNode,
        parse_boolean_query,
        build_keyword_qualifier,
        resolve_period,
        load_snapshots,
        save_snapshots,
        star_delta,
        elapsed_days,
        daily_velocity,
        format_velocity,
        format_repo,
        format_developer,
        build_export_row,
        build_dev_export_row,
        export_json,
        export_csv,
        write_output,
        apply_wildcards_to_keywords,
        load_ai_filter_config,
        apply_ai_filter,
    )
except ImportError:
    # Fallback: define minimal versions if legacy module unavailable
    VERSION = "3.0.0"
    PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}
    VALID_SEARCH_IN = {"name", "description", "readme"}
    VALID_KEYWORD_OPS = {"AND", "OR"}
    SNAPSHOT_DIR = Path.home() / ".daily-github-pulse"
    SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.json"


# ──────────────────────────────────────────────
# Multi-forge search
# ──────────────────────────────────────────────

def search_multi_forge(
    forge_names: list[str],
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    keyword_not: list[str] | None = None,
    search_in: str = "name,description",
    bool_query: object | None = None,
    gitea_url: str | None = None,
    workers: int = 4,
) -> dict[str, dict]:
    """Search multiple forges in parallel.

    Args:
        forge_names: List of forge identifiers.
        ... (same as single-forge search)

    Returns:
        Dict mapping forge name → {category: [ForgeRepo, ...]}
    """
    from forges import get_forge

    def _search_one(forge_name: str) -> tuple[str, dict]:
        kwargs = {}
        if forge_name == "gitea" and gitea_url:
            kwargs["base_url"] = f"{gitea_url.rstrip('/')}/api/v1"

        client = get_forge(forge_name, **kwargs)
        results = client.search_repos(
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
        return forge_name, results

    all_results = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(forge_names))) as pool:
        futures = {pool.submit(_search_one, name): name for name in forge_names}
        for future in as_completed(futures):
            forge_name = futures[future]
            try:
                _, results = future.result()
                all_results[forge_name] = results
            except Exception as exc:  # noqa: BLE001
                print(
                    f"  ⚠  {forge_name} search failed: {exc}",
                    file=sys.stderr,
                )

    if not all_results:
        print("  ✗  All forge searches failed.", file=sys.stderr)

    return all_results


def merge_forge_results(
    multi_results: dict[str, dict],
    top_n: int = 10,
) -> list:
    """Merge results from multiple forges into a single ranked list.

    Args:
        multi_results: Output of ``search_multi_forge()``.
        top_n:         Max total results.

    Returns:
        List of ForgeRepo sorted by stars (descending), capped at top_n.
    """
    from forges.base import ForgeRepo

    all_repos = []
    for forge_name, categories in multi_results.items():
        for repos in categories.values():
            all_repos.extend(repos)

    # Sort by stars descending
    all_repos.sort(key=lambda r: r.stars, reverse=True)
    return all_repos[:top_n]


def search_multi_forge_developers(
    forge_names: list[str],
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    gitea_url: str | None = None,
    workers: int = 4,
) -> list:
    """Search developers across multiple forges in parallel."""
    from forges import get_forge
    from forges.base import ForgeUser

    def _search_one(forge_name: str) -> tuple[str, list]:
        kwargs = {}
        if forge_name == "gitea" and gitea_url:
            kwargs["base_url"] = f"{gitea_url.rstrip('/')}/api/v1"

        client = get_forge(forge_name, **kwargs)
        results = client.search_developers(
            language=language,
            since_days=since_days,
            top_n=top_n,
        )
        return forge_name, results

    all_users = []
    with ThreadPoolExecutor(max_workers=min(workers, len(forge_names))) as pool:
        futures = {pool.submit(_search_one, name): name for name in forge_names}
        for future in as_completed(futures):
            forge_name = futures[future]
            try:
                _, users = future.result()
                all_users.extend(users)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"  ⚠  {forge_name} developer search failed: {exc}",
                    file=sys.stderr,
                )

    # Sort by followers descending
    all_users.sort(key=lambda u: u.followers, reverse=True)
    return all_users[:top_n]


# ──────────────────────────────────────────────
# Display helpers for ForgeRepo/ForgeUser
# ──────────────────────────────────────────────

def format_forge_repo(repo: "ForgeRepo", rank: int, snapshots: dict) -> str:
    """Format a ForgeRepo for plain-text display."""
    from forges.base import ForgeRepo

    delta = star_delta(
        {"stargazers_count": repo.stars, "full_name": repo.full_name},
        snapshots,
    )
    velocity = daily_velocity(
        {"stargazers_count": repo.stars, "full_name": repo.full_name},
        snapshots,
    )
    forge_label = f"[{repo.forge.upper()}]"
    desc = (repo.description or "No description")[:80]
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {forge_label} {repo.full_name}\n"
        f"    Stars: {repo.stars:,}  "
        f"Forks: {repo.forks:,}  "
        f"Lang: {repo.language or 'N/A'}\n"
        f"{format_velocity(delta, velocity)}\n"
        f"    Created: {repo.created_at[:10]}  |  Updated: {repo.updated_at[:10]}\n"
        f"    {desc}\n"
        f"    {repo.url}\n"
    )


def format_forge_user(user: "ForgeUser", rank: int) -> str:
    """Format a ForgeUser for plain-text display."""
    from forges.base import ForgeUser

    forge_label = f"[{user.forge.upper()}]"
    company = (user.company or "").strip().lstrip("@")
    return (
        f"#{rank}  {forge_label} {user.login}  ({user.name or user.login})\n"
        f"    Followers: {user.followers:,}  "
        f"Repos: {user.public_repos:,}  "
        f"Company: {company or 'N/A'}  "
        f"Location: {user.location or 'N/A'}\n"
        f"    {user.url}\n"
    )


def build_forge_export_row(repo: "ForgeRepo", rank: int, category: str, snapshots: dict) -> dict:
    """Build an export row from a ForgeRepo."""
    from forges.base import ForgeRepo

    delta = star_delta(
        {"stargazers_count": repo.stars, "full_name": repo.full_name},
        snapshots,
    )
    velocity = daily_velocity(
        {"stargazers_count": repo.stars, "full_name": repo.full_name},
        snapshots,
    )
    return {
        "rank": rank,
        "forge": repo.forge,
        "category": category,
        "full_name": repo.full_name,
        "stars": repo.stars,
        "star_delta": delta,
        "daily_velocity": velocity,
        "forks": repo.forks,
        "language": repo.language or "",
        "description": (repo.description or "").replace("\n", " ")[:200],
        "created_at": repo.created_at[:10],
        "updated_at": repo.updated_at[:10],
        "url": repo.url,
    }


def build_forge_dev_export_row(user: "ForgeUser", rank: int) -> dict:
    """Build an export row from a ForgeUser."""
    from forges.base import ForgeUser

    return {
        "rank": rank,
        "forge": user.forge,
        "login": user.login,
        "name": user.name or "",
        "company": (user.company or "").lstrip("@"),
        "location": user.location or "",
        "public_repos": user.public_repos,
        "followers": user.followers,
        "following": user.following,
        "url": user.url,
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="daily_github_pulse",
        description=(
            "Discover trending repositories and developers across all major "
            "forges — GitHub, GitLab, Gitea/Codeberg, Bitbucket — "
            "with real star velocity, boolean search, wildcard expansion, "
            "and AI relevance filtering."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Forge selection ─────────────────────────────────────────────────────
    parser.add_argument(
        "--forge", default="github", metavar="FORGES",
        help=(
            "Forge(s) to search. Comma-separated for multi-forge. "
            "Options: github (default), gitlab, gitea, bitbucket. "
            "Example: --forge github,gitlab"
        ),
    )
    parser.add_argument(
        "--gitea-url", default=None, metavar="URL",
        help=(
            "Base URL for Gitea instances (e.g. https://codeberg.org). "
            "Only used with --forge gitea."
        ),
    )

    # ── What to show ────────────────────────────────────────────────────────
    parser.add_argument(
        "--developers", action="store_true",
        help="Show trending developers instead of repositories.",
    )

    # ── Time window ─────────────────────────────────────────────────────────
    parser.add_argument(
        "-d", "--days", type=int, default=1, metavar="N",
        help="Look-back window in days (default: 1).  Overridden by --period.",
    )
    parser.add_argument(
        "-p", "--period", choices=list(PERIOD_DAYS), default=None,
        help="Named look-back period: day, week, month.  Overrides --days.",
    )

    # ── Filters ─────────────────────────────────────────────────────────────
    parser.add_argument(
        "-l", "--language", default=None, metavar="LANG",
        help="Filter by programming language (e.g. python, rust, go).",
    )
    parser.add_argument(
        "-n", "--top", type=int, default=10, metavar="N",
        help="Number of results per category (default: 10).",
    )

    # ── Keyword search ──────────────────────────────────────────────────────
    parser.add_argument(
        "-k", "--keyword", default=None, metavar="TERM",
        help="Single keyword filter (legacy; use --keywords for multiple terms).",
    )
    parser.add_argument(
        "--keywords", nargs="+", default=None, metavar="TERM",
        help="One or more keyword terms.  Combined with --keyword-op.",
    )
    parser.add_argument(
        "--keyword-op", choices=["AND", "OR"], default="AND",
        help="Boolean operator for --keywords (default: AND).",
    )
    parser.add_argument(
        "--keyword-not", nargs="+", default=None, metavar="TERM",
        help="Terms to exclude from --keywords search.",
    )
    parser.add_argument(
        "--search-in",
        default="name,description",
        metavar="FIELDS",
        help=(
            "Comma-separated fields to search in.  "
            "Valid: name, description, readme (default: name,description)."
        ),
    )
    parser.add_argument(
        "--bool-query", default=None, metavar="EXPR",
        help=(
            "Boolean keyword expression, e.g. "
            "'(LLM OR GPT) AND agent AND NOT benchmark'."
        ),
    )
    parser.add_argument(
        "--wildcard", action="store_true",
        help=(
            "Expand ? and * wildcards in --keywords against the NLTK word corpus.  "
            "Requires: pip install nltk"
        ),
    )

    # ── AI filter ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--ai-filter", action="store_true",
        help="Enable LLM-based relevance filtering.",
    )
    parser.add_argument(
        "--ai-filter-query", default=None, metavar="QUERY",
        help="Natural-language description of what you're looking for.",
    )
    parser.add_argument(
        "--ai-filter-fallback",
        choices=["fail", "passthrough"],
        default="fail",
        help=(
            "Behaviour when the LLM is unavailable: "
            "'fail' (default) exits with error; "
            "'passthrough' shows all repos unfiltered."
        ),
    )

    # ── Output ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "-o", "--output", choices=["text", "json", "csv"], default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "-f", "--output-file", default=None, metavar="PATH",
        help="Write output to this file instead of stdout.",
    )

    # ── Snapshot ─────────────────────────────────────────────────────────────
    parser.add_argument(
        "--no-snapshot", action="store_true",
        help="Skip saving star counts for velocity tracking this run.",
    )
    parser.add_argument(
        "--clear-snapshots", action="store_true",
        help="Delete all stored snapshots and exit.",
    )

    # ── Version ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}",
    )

    return parser


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    """Parse CLI arguments and run the requested search."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Clear snapshots and exit
    if args.clear_snapshots:
        if SNAPSHOT_FILE.exists():
            SNAPSHOT_FILE.unlink()
            print("  ✓  Snapshots cleared.", file=sys.stderr)
        else:
            print("  (no snapshots to clear)", file=sys.stderr)
        return

    # Resolve look-back window
    try:
        since_days = resolve_period(args.period, args.days)
    except ValueError as exc:
        parser.error(str(exc))

    # Parse forge list
    forge_names = [f.strip().lower() for f in args.forge.split(",") if f.strip()]
    if not forge_names:
        parser.error("--forge requires at least one forge name.")

    # ── Developer mode ──────────────────────────────────────────────────────
    if args.developers:
        if RICH_AVAILABLE and print_header:
            print_header(since_days, mode="developers")
        else:
            print(
                f"\n🔍  Trending Developers  "
                f"(last {since_days} day{'s' if since_days != 1 else ''})\n",
                file=sys.stderr,
            )

        if len(forge_names) == 1:
            from forges import get_forge
            client = get_forge(forge_names[0])
            developers = client.search_developers(
                language=args.language,
                since_days=since_days,
                top_n=args.top,
            )
        else:
            developers = search_multi_forge_developers(
                forge_names,
                language=args.language,
                since_days=since_days,
                top_n=args.top,
                gitea_url=args.gitea_url,
            )

        if args.output == "text":
            for i, user in enumerate(developers, start=1):
                print(format_forge_user(user, i))
        else:
            rows = [build_forge_dev_export_row(u, i) for i, u in enumerate(developers, start=1)]
            if args.output == "json":
                write_output(export_json(rows), args.output_file, "json")
            else:
                write_output(
                    export_csv(rows, ["rank", "forge"] + DEV_EXPORT_FIELDS[1:]),
                    args.output_file,
                    "csv",
                )
        return

    # ── Repository search ───────────────────────────────────────────────────
    if RICH_AVAILABLE and print_header:
        print_header(since_days, mode="repos")
    else:
        print(
            f"\n🔍  Trending Repositories  "
            f"(last {since_days} day{'s' if since_days != 1 else ''})\n",
            file=sys.stderr,
        )

    if len(forge_names) == 1:
        # Single forge — use ForgeClient directly
        from forges import get_forge
        client = get_forge(forge_names[0])

        # Boolean query parse
        bool_query_ast = None
        if args.bool_query:
            try:
                bool_query_ast = parse_boolean_query(args.bool_query)
            except ValueError as exc:
                parser.error(str(exc))

        # Wildcard expansion
        effective_keywords = args.keywords
        if args.wildcard and effective_keywords:
            effective_keywords = apply_wildcards_to_keywords(effective_keywords)

        repos_by_category = client.search_repos(
            language=args.language,
            since_days=since_days,
            top_n=args.top,
            keyword=args.keyword,
            keywords=effective_keywords,
            keyword_op=args.keyword_op,
            keyword_not=args.keyword_not,
            search_in=args.search_in,
            bool_query=bool_query_ast,
        )
    else:
        # Multi-forge — parallel search, merge results
        bool_query_ast = None
        if args.bool_query:
            try:
                bool_query_ast = parse_boolean_query(args.bool_query)
            except ValueError as exc:
                parser.error(str(exc))

        effective_keywords = args.keywords
        if args.wildcard and effective_keywords:
            effective_keywords = apply_wildcards_to_keywords(effective_keywords)

        multi_results = search_multi_forge(
            forge_names,
            language=args.language,
            since_days=since_days,
            top_n=args.top,
            keyword=args.keyword,
            keywords=effective_keywords,
            keyword_op=args.keyword_op,
            keyword_not=args.keyword_not,
            search_in=args.search_in,
            bool_query=bool_query_ast,
            gitea_url=args.gitea_url,
        )

        # Convert to unified format: merge all repos into a single category
        merged = merge_forge_results(multi_results, top_n=args.top)
        repos_by_category = {"All Forges": merged}

    # ── AI filter ───────────────────────────────────────────────────────────
    if args.ai_filter:
        ai_query = args.ai_filter_query
        if not ai_query:
            parser.error("--ai-filter requires --ai-filter-query.")

        ai_config = load_ai_filter_config()
        if ai_config is None:
            if args.ai_filter_fallback == "passthrough":
                print(
                    "  ⚠  No AI credentials found — showing all results unfiltered.",
                    file=sys.stderr,
                )
            else:
                print(
                    "  ✗  No AI credentials found.  "
                    "Set AI_API_KEY (or ANTHROPIC_API_KEY) in .env.\n"
                    "     Use --ai-filter-fallback=passthrough to skip filtering.",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(
                f"  🤖  AI filter active  [{ai_config.provider} / {ai_config.model}]\n"
                f"      Query: \"{ai_query}\"\n",
                file=sys.stderr,
            )
            try:
                repos_by_category = apply_ai_filter(
                    repos_by_category,
                    query=ai_query,
                    config=ai_config,
                    fallback=args.ai_filter_fallback,
                    verbose=True,
                )
            except RuntimeError as exc:
                print(f"AI filter error: {exc}", file=sys.stderr)
                sys.exit(1)

    # ── Load snapshots for velocity ─────────────────────────────────────────
    snapshots = load_snapshots()

    # ── Render output ───────────────────────────────────────────────────────
    if args.output == "text":
        if RICH_AVAILABLE and print_repo_table:
            print_repo_table(repos_by_category, snapshots)
        else:
            from forges.base import ForgeRepo as _ForgeRepo

            for category, repos in repos_by_category.items():
                print(f"\n{'─' * 70}")
                print(f"  {category.upper()}  ({len(repos)} results)")
                print(f"{'─' * 70}\n")
                if not repos:
                    print("  (no results)\n")
                    continue
                for i, repo in enumerate(repos, start=1):
                    if isinstance(repo, _ForgeRepo):
                        print(format_forge_repo(repo, i, snapshots))
                    else:
                        print(format_repo(repo, i, snapshots))
    else:
        from forges.base import ForgeRepo as _ForgeRepo

        all_rows = []
        for category, repos in repos_by_category.items():
            for i, repo in enumerate(repos, start=1):
                if isinstance(repo, _ForgeRepo):
                    all_rows.append(build_forge_export_row(repo, i, category, snapshots))
                else:
                    all_rows.append(build_export_row(repo, i, category, snapshots))

        # Add forge column to export fields
        export_fields = ["rank", "forge"] + [f for f in EXPORT_FIELDS if f != "rank"]

        if args.output == "json":
            write_output(export_json(all_rows), args.output_file, "json")
        else:
            write_output(export_csv(all_rows, export_fields), args.output_file, "csv")

    # ── Persist snapshots ───────────────────────────────────────────────────
    if not args.no_snapshot:
        try:
            save_snapshots(repos_by_category)
        except OSError as exc:
            print(f"  ⚠  Could not save snapshots: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
