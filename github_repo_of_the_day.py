#!/usr/bin/env python3
"""
daily-github-pulse  v1.4.0
──────────────────────────
Discover GitHub's top repositories of the day — with real star velocity.

How velocity works
──────────────────
On each run, star counts are saved to a local snapshot file:
  ~/.daily-github-pulse/snapshots.json

On the next run, the previous snapshot is loaded and the delta
(stars gained since last run) is shown next to each repo.
No external API calls or scraping — pure local arithmetic.

Token priority
──────────────
  1. --token CLI flag
  2. GITHUB_TOKEN environment variable / .env file
  3. Unauthenticated  →  60 req/hr limit
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VERSION = "1.4.0"
SNAPSHOT_DIR = Path.home() / ".daily-github-pulse"
SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.json"

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")

# Named period shortcuts → number of days
PERIOD_DAYS: dict[str, int] = {
    "day":   1,
    "week":  7,
    "month": 30,
}

# Fields included in JSON / CSV exports (in order)
EXPORT_FIELDS = [
    "rank",
    "category",
    "full_name",
    "stars",
    "star_delta",
    "forks",
    "language",
    "description",
    "created_at",
    "updated_at",
    "url",
]


# ──────────────────────────────────────────────
# GitHub API helpers
# ──────────────────────────────────────────────
def get_headers() -> dict:
    """Build HTTP headers for the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# ──────────────────────────────────────────────
# Period helpers
# ──────────────────────────────────────────────
def resolve_period(period: str | None, days: int) -> int:
    """
    Resolve the effective look-back window in days.

    ``--period`` takes precedence over ``--days`` when both are supplied.
    Valid period tokens are ``day`` (1), ``week`` (7), and ``month`` (30).

    Args:
        period: Named period string (``"day"``, ``"week"``, ``"month"``),
                or ``None`` when ``--period`` was not used.
        days:   Numeric fallback from ``--days`` (default: 1).

    Returns:
        Resolved number of look-back days.

    Raises:
        ValueError: If ``period`` is not a recognised token.

    Examples:
        >>> resolve_period("week", 1)
        7
        >>> resolve_period(None, 3)
        3
        >>> resolve_period("month", 99)
        30
    """
    if period is None:
        return days
    key = period.strip().lower()
    if key not in PERIOD_DAYS:
        raise ValueError(
            f"Unknown period '{period}'. Valid options: "
            + ", ".join(PERIOD_DAYS)
        )
    return PERIOD_DAYS[key]


# ──────────────────────────────────────────────
# Snapshot helpers
# ──────────────────────────────────────────────
def load_snapshots() -> dict:
    """
    Load previously saved star counts from disk.

    Returns:
        dict mapping repo full_name -> {"stars": int, "saved_at": ISO string}.
        Empty dict if the file does not exist or is corrupted.
    """
    if not SNAPSHOT_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(repos_by_category: dict) -> None:
    """
    Persist current star counts to disk, merging with existing data.

    Args:
        repos_by_category: output of search_trending_repos().
    """
    existing = load_snapshots()
    now = datetime.utcnow().isoformat()

    for repos in repos_by_category.values():
        for repo in repos:
            existing[repo["full_name"]] = {
                "stars": repo["stargazers_count"],
                "saved_at": now,
            }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def star_delta(repo: dict, snapshots: dict) -> int | None:
    """
    Calculate stars gained since the last snapshot.

    Args:
        repo:      repo dict from GitHub API.
        snapshots: loaded snapshot data.

    Returns:
        int delta, or None if no previous snapshot exists for this repo.

    Examples:
        >>> snapshots = {"owner/repo": {"stars": 12400, "saved_at": "..."}}
        >>> repo = {"full_name": "owner/repo", "stargazers_count": 12542}
        >>> star_delta(repo, snapshots)
        142
    """
    prev = snapshots.get(repo["full_name"])
    if prev is None:
        return None
    return repo["stargazers_count"] - prev["stars"]


# ──────────────────────────────────────────────
# Core search
# ──────────────────────────────────────────────
def search_trending_repos(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    search_in: str = "name,description",
) -> dict:
    """
    Query the GitHub Search API and return top repositories by category.

    Uses two complementary strategies since GitHub has no official trending
    endpoint:

    - New Today     — recently created repos with >10 stars (newcomers).
    - Active Giants — recently pushed repos with >1000 stars (veterans).

    Repos appearing in both result sets are deduplicated — shown only in
    the first category that returns them.

    Args:
        language:   Optional language filter (e.g. "python", "rust").
        since_days: Days to look back (default: 1 = today).
        top_n:      Max results per category; GitHub hard limit is 100.
        keyword:    Optional keyword to match against repo metadata.
        search_in:  Comma-separated search scope for keyword.
                    Valid tokens: "name", "description", "readme".
                    Default: "name,description".
                    Warning: "readme" is significantly slower.

    Returns:
        dict: {category_label: [repo_dict, ...]}

    Raises:
        requests.HTTPError, requests.ConnectionError, requests.Timeout
    """
    since_date = (date.today() - timedelta(days=since_days)).isoformat()
    keyword_qualifier = f" {keyword} in:{search_in}" if keyword else ""

    queries = {
        "New Today": f"created:>={since_date} stars:>10{keyword_qualifier}",
        "Active Giants": f"pushed:>={since_date} stars:>1000{keyword_qualifier}",
    }
    if language:
        queries = {k: v + f" language:{language}" for k, v in queries.items()}

    results: dict = {}
    seen_ids: set = set()

    for label, query in queries.items():
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=get_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": top_n},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        unique = [r for r in items if r["id"] not in seen_ids]
        seen_ids.update(r["id"] for r in unique)
        results[label] = unique

    return results


# ──────────────────────────────────────────────
# Export helpers
# ──────────────────────────────────────────────
def build_export_row(repo: dict, rank: int, category: str, snapshots: dict) -> dict:
    """
    Build a flat export record from a repo dict.

    Extracts and renames the fields defined in EXPORT_FIELDS.
    The ``star_delta`` field is ``null`` / empty string when no previous
    snapshot exists for this repo.

    Args:
        repo:      repo dict from GitHub API.
        rank:      1-based rank within its category.
        category:  category label (e.g. "New Today").
        snapshots: loaded snapshot data.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    delta = star_delta(repo, snapshots)
    return {
        "rank":        rank,
        "category":    category,
        "full_name":   repo["full_name"],
        "stars":       repo["stargazers_count"],
        "star_delta":  delta,           # None → null in JSON, "" in CSV
        "forks":       repo["forks_count"],
        "language":    repo.get("language") or "",
        "description": (repo.get("description") or "").replace("\n", " "),
        "created_at":  repo["created_at"][:10],
        "updated_at":  repo["updated_at"][:10],
        "url":         repo["html_url"],
    }


def export_json(rows: list[dict]) -> str:
    """
    Serialise export rows to a JSON string.

    Args:
        rows: list of dicts as returned by build_export_row().

    Returns:
        Pretty-printed JSON string (2-space indent, ensure_ascii=False).
    """
    return json.dumps(rows, indent=2, ensure_ascii=False)


def export_csv(rows: list[dict]) -> str:
    """
    Serialise export rows to a CSV string.

    Uses the standard ``csv`` module with ``utf-8-sig`` BOM encoding so
    the file opens correctly in Excel and LibreOffice without manual
    encoding selection.

    ``None`` values (star_delta on first run) are written as empty strings.

    Args:
        rows: list of dicts as returned by build_export_row().

    Returns:
        CSV string with header row and one data row per repo.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=EXPORT_FIELDS,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        # Replace None with empty string for clean CSV output
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()


def write_output(content: str, output_file: str | None, fmt: str) -> None:
    """
    Write export content to a file or stdout.

    Args:
        content:     String content to write (JSON or CSV).
        output_file: File path string, or None to write to stdout.
        fmt:         Format label used only in the confirmation message
                     when writing to a file ("json" or "csv").
    """
    if output_file:
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        Path(output_file).write_text(content, encoding=encoding)
        print(f"  Exported {fmt.upper()} → {output_file}", file=sys.stderr)
    else:
        print(content)


# ──────────────────────────────────────────────
# Text formatting (human-readable)
# ──────────────────────────────────────────────
def format_velocity(delta: int | None) -> str:
    """
    Render a star delta as a human-readable velocity badge.

    Examples:
        >>> format_velocity(None)
        '  Δ  — (first run — no velocity data yet)'
        >>> format_velocity(142)
        '  Δ +142 ⭐ since last run'
        >>> format_velocity(-3)
        '  Δ -3 ⭐ since last run'
    """
    if delta is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    return f"  Δ {sign}{delta:,} ⭐ since last run"


def format_repo(repo: dict, rank: int, snapshots: dict) -> str:
    """
    Format a single repo dict into a human-readable terminal block.

    Args:
        repo:      repo dict from GitHub API.
        rank:      1-based display rank within its category.
        snapshots: loaded snapshot data for velocity calculation.

    Returns:
        Multi-line string ending with a trailing newline.
    """
    delta = star_delta(repo, snapshots)
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {repo['full_name']}\n"
        f"    Stars: {repo['stargazers_count']:,}  "
        f"Forks: {repo['forks_count']:,}  "
        f"Lang: {repo.get('language') or 'N/A'}\n"
        f"{format_velocity(delta)}\n"
        f"    Created: {repo['created_at'][:10]}  |  Updated: {repo['updated_at'][:10]}\n"
        f"    {(repo.get('description') or 'No description')[:80]}\n"
        f"    {repo['html_url']}\n"
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def find_repo_of_the_day(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    search_in: str = "name,description",
    use_snapshots: bool = True,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
) -> None:
    """
    Fetch, display/export, and optionally snapshot the top repos of the day.

    Orchestration order:
      1. Print session header (text mode only).
      2. Load previous snapshot (if use_snapshots).
      3. Fetch repos via search_trending_repos().
      4. Render output in the requested format.
      5. Save new snapshot baseline (if use_snapshots).

    Args:
        language:    Language filter. Default: None (all languages).
        since_days:  Days to look back. Default: 1.
        top_n:       Repos per category. Default: 10.
        keyword:     Keyword filter. Default: None.
        search_in:   Search scope for keyword. Default: "name,description".
        use_snapshots: Load/save velocity snapshots. Default: True.
        output_fmt:  Output format: "text" (default), "json", or "csv".
        output_file: Write output to this file path instead of stdout.
                     Confirmation message is printed to stderr.

    Returns:
        None

    Raises:
        SystemExit(1): On GitHub API errors.
    """
    # Header is only useful for human readers
    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        if language:
            print(f"  Language : {language}")
        if keyword:
            print(f"  Keyword  : '{keyword}'  in [{search_in}]")
        auth = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
        print(f"  Auth     : {auth}")
        snap_status = "enabled" if use_snapshots else "disabled (--no-snapshot)"
        print(f"  Velocity : {snap_status}")
        print(f"{'#' * 70}\n")

    snapshots = load_snapshots() if use_snapshots else {}

    try:
        all_results = search_trending_repos(
            language=language,
            since_days=since_days,
            top_n=top_n,
            keyword=keyword,
            search_in=search_in,
        )
    except requests.HTTPError as exc:
        print(f"[ERROR] GitHub API returned: {exc}", file=sys.stderr)
        if not GITHUB_TOKEN:
            print("  Tip: set GITHUB_TOKEN in .env to raise rate limit to 5,000 req/hr.",
                  file=sys.stderr)
        sys.exit(1)
    except requests.ConnectionError:
        print("[ERROR] Could not reach GitHub API. Check your internet connection.",
              file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print("[ERROR] GitHub API request timed out. Try again in a moment.",
              file=sys.stderr)
        sys.exit(1)

    # ─ Render output ─────────────────────────────────────────
    if output_fmt == "text":
        for category, repos in all_results.items():
            print(f"\n{'─' * 70}")
            print(f"  {category}")
            print(f"{'─' * 70}")
            if not repos:
                print("  No repositories found.\n")
                continue
            for i, repo in enumerate(repos, 1):
                print(format_repo(repo, i, snapshots))

    else:
        # Build flat list of export rows across all categories
        rows: list[dict] = []
        for category, repos in all_results.items():
            for i, repo in enumerate(repos, 1):
                rows.append(build_export_row(repo, i, category, snapshots))

        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows), output_file, "csv")

    # ─ Save snapshot ───────────────────────────────────────
    if use_snapshots:
        save_snapshots(all_results)
        if output_fmt == "text":
            print(f"\n  Snapshot saved → {SNAPSHOT_FILE}")
        else:
            print(f"  Snapshot saved → {SNAPSHOT_FILE}", file=sys.stderr)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="daily-github-pulse",
        description="Find GitHub top repos of the day — with real star velocity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: today's top repos, all languages
  python github_repo_of_the_day.py

  # Named period shortcut (day / week / month)
  python github_repo_of_the_day.py --period week
  python github_repo_of_the_day.py --period month --language rust

  # Numeric fallback (--days still works)
  python github_repo_of_the_day.py --days 14

  # Top Python repos
  python github_repo_of_the_day.py --language python

  # Export as JSON to stdout
  python github_repo_of_the_day.py --output json

  # Export as CSV to a file
  python github_repo_of_the_day.py --output csv --output-file results.csv

  # JSON export, pipe into jq
  python github_repo_of_the_day.py --output json | jq '.[].full_name'

  # Search by keyword
  python github_repo_of_the_day.py --keyword "LLM agent" --output json

  # Search in README too (slower)
  python github_repo_of_the_day.py --keyword "MCP server" --search-in name,description,readme

  # Skip velocity tracking
  python github_repo_of_the_day.py --no-snapshot

  # Reset stored snapshots
  python github_repo_of_the_day.py --clear-snapshots

Token setup:
  Create a .env file:  GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
  Add .env to .gitignore.
  Get a token: https://github.com/settings/tokens
        """,
    )

    parser.add_argument("--language", "-l", metavar="LANG",
                        help="Filter by language (e.g. python, go, rust)")
    parser.add_argument(
        "--period", "-p",
        choices=["day", "week", "month"],
        metavar="PERIOD",
        help="Named look-back window: day (1), week (7), month (30). "
             "Takes precedence over --days when both are supplied.",
    )
    parser.add_argument("--days", "-d", type=int, default=1, metavar="N",
                        help="Look back N days (default: 1 = today). "
                             "Ignored when --period is used.")
    parser.add_argument("--top", "-n", type=int, default=10, metavar="N",
                        help="Repos per category (default: 10)")
    parser.add_argument("--token", "-t", metavar="TOKEN",
                        help="GitHub PAT — overrides .env")
    parser.add_argument("--keyword", "-k", metavar="WORD",
                        help="Keyword to search (e.g. 'LLM agent', 'vector database')")
    parser.add_argument(
        "--search-in", "-s",
        default="name,description",
        metavar="SCOPE",
        help=(
            "Where to search the keyword: name, description, readme "
            "(comma-separated, default: name,description). "
            "Note: 'readme' is significantly slower."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        choices=["text", "json", "csv"],
        default="text",
        metavar="FORMAT",
        help="Output format: text (default), json, csv",
    )
    parser.add_argument(
        "--output-file", "-f",
        metavar="FILE",
        help="Write output to FILE instead of stdout (json/csv only)",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Disable snapshot save/load for this run",
    )
    parser.add_argument(
        "--clear-snapshots",
        action="store_true",
        help=f"Delete all stored snapshots and exit ({SNAPSHOT_FILE})",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    if args.token:
        GITHUB_TOKEN = args.token

    if args.clear_snapshots:
        if SNAPSHOT_FILE.exists():
            SNAPSHOT_FILE.unlink()
            print(f"Snapshots cleared: {SNAPSHOT_FILE}")
        else:
            print("No snapshot file found.")
        sys.exit(0)

    effective_days = resolve_period(args.period, args.days)

    find_repo_of_the_day(
        language=args.language,
        since_days=effective_days,
        top_n=args.top,
        keyword=args.keyword,
        search_in=args.search_in,
        use_snapshots=not args.no_snapshot,
        output_fmt=args.output,
        output_file=args.output_file,
    )
