#!/usr/bin/env python3
"""
daily-github-pulse  v1.2.0
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

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VERSION = "1.2.0"
SNAPSHOT_DIR = Path.home() / ".daily-github-pulse"
SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.json"

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")


# ──────────────────────────────────────────────
# GitHub API helpers
# ──────────────────────────────────────────────
def get_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# ──────────────────────────────────────────────
# Snapshot helpers
# ──────────────────────────────────────────────
def load_snapshots() -> dict:
    """
    Load previously saved star counts from disk.

    Returns:
        dict mapping repo full_name -> {"stars": int, "saved_at": ISO string}
        Empty dict if file does not exist or is corrupted.
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
        repos_by_category: output of search_trending_repos()
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
    Calculate stars gained since the last snapshot for a repo.

    Args:
        repo:      repo dict from GitHub API
        snapshots: loaded snapshot data

    Returns:
        int delta (can be negative if stars were lost),
        or None if no previous snapshot exists for this repo.
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
    Query GitHub Search API using two complementary strategies:

      New Today     — repos created recently with >10 stars
                      (fast-rising newcomers)
      Active Giants — repos pushed today with >1000 stars
                      (established projects still actively maintained)

    Note: GitHub has no official trending endpoint. Total stars are used as a
    proxy for popularity. Use star_delta() to get velocity (daily gain).

    Args:
        language:   Optional language filter (e.g. "python", "rust")
        since_days: How many days back to look (default: 1 = today)
        top_n:      Max results per category (max 100 per GitHub API)
        keyword:    Optional keyword to search inside repos
        search_in:  Comma-separated scope for keyword search.
                    Valid values: "name", "description", "readme"
                    or any combination thereof.
                    Default: "name,description"
                    ⚠ Including "readme" significantly increases response time.

    Returns:
        dict mapping category label (str) -> list of repo dicts
        Repos that appear in multiple categories are deduplicated — they
        appear only in the first category that returns them.
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
    seen_ids: set = set()  # cross-category deduplication

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
# Formatting
# ──────────────────────────────────────────────
def format_velocity(delta: int | None) -> str:
    """
    Render star delta as a human-readable badge.

    Examples:
        None  →  "  (first run — no velocity data)"
        0     →  "  Δ  0 ⭐ since last run"
        142   →  "  Δ +142 ⭐ since last run"
        -3    →  "  Δ  -3 ⭐ since last run"
    """
    if delta is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    return f"  Δ {sign}{delta:,} ⭐ since last run"


def format_repo(repo: dict, rank: int, snapshots: dict) -> str:
    """
    Format a single repo dict into a human-readable block.

    Args:
        repo:      repo dict from GitHub API
        rank:      display rank (1-indexed)
        snapshots: loaded snapshot data for velocity calculation
    """
    delta = star_delta(repo, snapshots)
    velocity_line = format_velocity(delta)

    return (
        f"{'=' * 70}\n"
        f"#{rank}  {repo['full_name']}\n"
        f"    Stars: {repo['stargazers_count']:,}  "
        f"Forks: {repo['forks_count']:,}  "
        f"Lang: {repo.get('language') or 'N/A'}\n"
        f"{velocity_line}\n"
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
) -> None:
    """Fetch, display, and optionally snapshot top repos of the day."""
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

    # Load previous snapshots before the API call
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
        print(f"[ERROR] GitHub API returned: {exc}")
        if not GITHUB_TOKEN:
            print("  Tip: set GITHUB_TOKEN in .env to raise rate limit to 5,000 req/hr.")
        sys.exit(1)
    except requests.ConnectionError:
        print("[ERROR] Could not reach GitHub API. Check your internet connection.")
        sys.exit(1)
    except requests.Timeout:
        print("[ERROR] GitHub API request timed out. Try again in a moment.")
        sys.exit(1)

    for category, repos in all_results.items():
        print(f"\n{'─' * 70}")
        print(f"  {category}")
        print(f"{'─' * 70}")
        if not repos:
            print("  No repositories found.\n")
            continue
        for i, repo in enumerate(repos, 1):
            print(format_repo(repo, i, snapshots))

    # Save current run as new snapshot baseline
    if use_snapshots:
        save_snapshots(all_results)
        print(f"\n  Snapshot saved → {SNAPSHOT_FILE}")


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

  # Top Python repos
  python github_repo_of_the_day.py --language python

  # Search by keyword in name + description
  python github_repo_of_the_day.py --keyword "LLM agent"

  # Search in README too (slower)
  python github_repo_of_the_day.py --keyword "vector database" --search-in name,description,readme

  # Combine language + keyword + top N
  python github_repo_of_the_day.py --language python --keyword "agent" --top 5

  # Skip velocity tracking for this run
  python github_repo_of_the_day.py --no-snapshot

  # Reset all stored snapshots
  python github_repo_of_the_day.py --clear-snapshots

Token setup:
  Create a .env file containing:  GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
  Then add .env to .gitignore.
  Get a token: https://github.com/settings/tokens
        """,
    )

    parser.add_argument("--language", "-l", metavar="LANG",
                        help="Filter by language (e.g. python, go, rust)")
    parser.add_argument("--days", "-d", type=int, default=1, metavar="N",
                        help="Look back N days (default: 1 = today)")
    parser.add_argument("--top", "-n", type=int, default=10, metavar="N",
                        help="Repos per category (default: 10)")
    parser.add_argument("--token", "-t", metavar="TOKEN",
                        help="GitHub PAT — overrides .env")
    parser.add_argument("--keyword", "-k", metavar="WORD",
                        help="Keyword to search (e.g. 'vector database', 'LLM agent')")
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
        "--no-snapshot",
        action="store_true",
        help="Disable snapshot save/load for this run (velocity data will not be shown)",
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

    find_repo_of_the_day(
        language=args.language,
        since_days=args.days,
        top_n=args.top,
        keyword=args.keyword,
        search_in=args.search_in,
        use_snapshots=not args.no_snapshot,
    )
