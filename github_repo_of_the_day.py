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
    """
    Build HTTP request headers for the GitHub REST API.

    Reads the module-level ``GITHUB_TOKEN`` variable.  When a token is
    present the ``Authorization`` header is included, which raises the
    API rate limit from 60 to 5,000 requests per hour.

    Returns:
        dict: Headers dict ready to pass to ``requests.get()``.
              Always includes ``Accept: application/vnd.github+json``.
              Includes ``Authorization: Bearer <token>`` when
              ``GITHUB_TOKEN`` is set.

    Examples:
        >>> import github_repo_of_the_day as m
        >>> m.GITHUB_TOKEN = None
        >>> m.get_headers()
        {'Accept': 'application/vnd.github+json'}

        >>> m.GITHUB_TOKEN = 'ghp_test'
        >>> m.get_headers()
        {'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ghp_test'}
    """
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

    Reads ``~/.daily-github-pulse/snapshots.json``.  The file is created
    automatically by :func:`save_snapshots` after each successful run.
    Corrupt or missing files are handled gracefully — an empty dict is
    returned instead of raising an exception.

    Returns:
        dict: Mapping of ``repo_full_name`` (str) to a snapshot record::

                {
                    "owner/repo": {
                        "stars": 12400,
                        "saved_at": "2026-06-01T10:30:00"
                    },
                    ...
                }

              Returns ``{}`` when the snapshot file does not exist or
              cannot be parsed.

    Examples:
        >>> # First run — no file yet
        >>> load_snapshots()
        {}

        >>> # After a successful run the file exists
        >>> load_snapshots()
        {'owner/repo': {'stars': 12400, 'saved_at': '2026-06-01T10:30:00'}}
    """
    if not SNAPSHOT_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(repos_by_category: dict) -> None:
    """
    Persist current star counts to disk, merging with existing snapshot data.

    Creates ``~/.daily-github-pulse/`` if it does not exist.
    Existing entries are preserved; entries for repos seen in this run
    are overwritten with the latest star count and timestamp.

    Args:
        repos_by_category (dict): Return value of :func:`search_trending_repos`.
            Structure::

                {
                    "New Today": [<repo_dict>, ...],
                    "Active Giants": [<repo_dict>, ...]
                }

            Each repo dict must contain at least ``full_name`` (str) and
            ``stargazers_count`` (int).

    Returns:
        None

    Raises:
        OSError: If the snapshot directory cannot be created or the file
            cannot be written (e.g. permission denied).

    Examples:
        >>> repos = {"New Today": [{"full_name": "a/b", "stargazers_count": 100}]}
        >>> save_snapshots(repos)   # writes ~/.daily-github-pulse/snapshots.json
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
    Calculate stars gained since the last snapshot for a single repo.

    Compares the repo's current ``stargazers_count`` against the value
    stored in the most recent snapshot.  A negative result means the repo
    lost stars (uncommon but possible after spam cleanup).

    Args:
        repo (dict): Repo dict from the GitHub Search API.  Must contain:
            - ``full_name`` (str): e.g. ``"owner/repo"``
            - ``stargazers_count`` (int): current total star count
        snapshots (dict): Loaded snapshot data as returned by
            :func:`load_snapshots`.

    Returns:
        int | None:
            - ``int`` — star delta since last snapshot (positive, zero, or
              negative).
            - ``None`` — no previous snapshot exists for this repo (first
              time it appears in results).

    Examples:
        >>> snapshots = {"owner/repo": {"stars": 12400, "saved_at": "..."}}
        >>> repo = {"full_name": "owner/repo", "stargazers_count": 12542}
        >>> star_delta(repo, snapshots)
        142

        >>> repo_new = {"full_name": "owner/new", "stargazers_count": 50}
        >>> star_delta(repo_new, snapshots) is None
        True

        >>> repo_loss = {"full_name": "owner/repo", "stargazers_count": 12397}
        >>> star_delta(repo_loss, snapshots)
        -3
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

    Uses two complementary search strategies to approximate trending
    activity, since GitHub provides no official trending API endpoint:

    - **New Today** — repos created within the last ``since_days`` days
      with more than 10 stars.  Catches fast-rising newcomers.
    - **Active Giants** — repos pushed within the last ``since_days`` days
      with more than 1,000 stars.  Catches established projects that are
      still actively maintained and generating engagement.

    Both queries sort by total stars descending.  A repo that appears in
    both result sets is shown only once (in whichever category returns it
    first) — see the deduplication guarantee below.

    Args:
        language (str | None): Optional programming language filter.
            Must match GitHub's language identifiers (case-insensitive),
            e.g. ``"python"``, ``"typescript"``, ``"rust"``.
            Defaults to ``None`` (all languages).
        since_days (int): How many calendar days back to include.
            ``1`` means today only (since midnight UTC).
            Defaults to ``1``.
        top_n (int): Maximum number of results per category.
            GitHub Search API hard limit is 100.
            Defaults to ``10``.
        keyword (str | None): Optional free-text keyword to match against
            repo metadata.  The scope is controlled by ``search_in``.
            Defaults to ``None`` (no keyword filter).
        search_in (str): Comma-separated list of fields to search the
            keyword in.  Valid tokens: ``"name"``, ``"description"``,
            ``"readme"``.  Any combination is accepted.
            Defaults to ``"name,description"``.

            .. warning::
                Including ``"readme"`` triggers GitHub’s full-text index
                and can increase response time to 10–15 seconds.

    Returns:
        dict: Ordered mapping of category label → list of repo dicts::

                {
                    "New Today":     [<repo_dict>, ...],
                    "Active Giants": [<repo_dict>, ...]
                }

            Each repo dict is the raw object returned by the GitHub Search
            API (see https://docs.github.com/en/rest/search/search).  Key
            fields used downstream: ``id``, ``full_name``,
            ``stargazers_count``, ``forks_count``, ``language``,
            ``description``, ``created_at``, ``updated_at``,
            ``html_url``.

            **Deduplication guarantee**: a repo whose ``id`` already
            appeared in an earlier category is excluded from all
            subsequent categories.

    Raises:
        requests.HTTPError: Raised (via ``raise_for_status()``) when the
            GitHub API returns a 4xx or 5xx status.  Common causes:
            - 403 Forbidden — rate limit exceeded (add a token).
            - 422 Unprocessable Entity — malformed query string.
        requests.ConnectionError: No network connectivity.
        requests.Timeout: GitHub did not respond within 15 seconds.

    Examples:
        >>> # Unauthenticated, today only, all languages
        >>> results = search_trending_repos()
        >>> list(results.keys())
        ['New Today', 'Active Giants']

        >>> # Top 5 Python repos, last 7 days
        >>> results = search_trending_repos(language="python", since_days=7, top_n=5)
        >>> all(len(v) <= 5 for v in results.values())
        True

        >>> # Keyword search scoped to name + description
        >>> results = search_trending_repos(keyword="LLM agent", search_in="name,description")
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
# Formatting
# ──────────────────────────────────────────────
def format_velocity(delta: int | None) -> str:
    """
    Render a star delta value as a human-readable velocity badge.

    The returned string is indented with two leading spaces so it aligns
    with other lines inside :func:`format_repo`.

    Args:
        delta (int | None):
            - ``None``  — no previous snapshot exists (first run).
            - ``int``   — signed star count change since last snapshot.
              Positive means growth; negative means star loss.

    Returns:
        str: A single-line velocity string, no trailing newline.

    Examples:
        >>> format_velocity(None)
        '  Δ  — (first run — no velocity data yet)'

        >>> format_velocity(0)
        '  Δ 0 ⭐ since last run'

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
    Format a single GitHub repo dict into a human-readable display block.

    Produces a multi-line string suitable for printing to the terminal.
    The velocity line is computed on the fly from the provided snapshot
    data via :func:`star_delta` and :func:`format_velocity`.

    Args:
        repo (dict): Repo dict from the GitHub Search API.  Expected keys:
            - ``full_name``        (str)  — e.g. ``"owner/repo"``
            - ``stargazers_count`` (int)  — total stars
            - ``forks_count``      (int)  — total forks
            - ``language``         (str | None) — primary language
            - ``description``      (str | None) — short description
            - ``created_at``       (str)  — ISO 8601 creation timestamp
            - ``updated_at``       (str)  — ISO 8601 last-update timestamp
            - ``html_url``         (str)  — browser URL
        rank (int): 1-based display rank within its category.
        snapshots (dict): Loaded snapshot data as returned by
            :func:`load_snapshots`.  Pass ``{}`` to suppress velocity.

    Returns:
        str: Multi-line formatted block ending with a trailing newline.
            Structure::

                ======================================================================
                #1  owner/repo
                    Stars: 12,542  Forks: 834  Lang: Python
                      Δ +142 ⭐ since last run
                    Created: 2025-03-10  |  Updated: 2026-06-01
                    A short description (truncated to 80 chars)
                    https://github.com/owner/repo

    Examples:
        >>> repo = {
        ...     "full_name": "owner/repo",
        ...     "stargazers_count": 12542,
        ...     "forks_count": 834,
        ...     "language": "Python",
        ...     "description": "A test repo",
        ...     "created_at": "2025-03-10T00:00:00Z",
        ...     "updated_at": "2026-06-01T00:00:00Z",
        ...     "html_url": "https://github.com/owner/repo",
        ... }
        >>> print(format_repo(repo, 1, {}))   # no snapshot → first-run velocity
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
    """
    Fetch, display, and optionally snapshot the top GitHub repos of the day.

    This is the main orchestrator function called by the CLI.  It:

    1. Prints a session header with active filters and auth status.
    2. Loads the previous snapshot (if ``use_snapshots`` is ``True``).
    3. Calls :func:`search_trending_repos` to fetch results.
    4. Prints each repo via :func:`format_repo`, including velocity.
    5. Saves a new snapshot baseline (if ``use_snapshots`` is ``True``).

    Args:
        language (str | None): Programming language filter passed through
            to :func:`search_trending_repos`.  Defaults to ``None``.
        since_days (int): Number of days to look back.  Defaults to ``1``.
        top_n (int): Repos per category.  Defaults to ``10``.
        keyword (str | None): Keyword filter.  Defaults to ``None``.
        search_in (str): Comma-separated search scope for keyword.
            Defaults to ``"name,description"``.
        use_snapshots (bool): When ``True`` (default), load the previous
            snapshot before fetching and save a new one after.  Set to
            ``False`` (``--no-snapshot``) to run without any disk I/O.

    Returns:
        None

    Raises:
        SystemExit(1): On any GitHub API error (HTTP, connection, or
            timeout).  An informative message is printed before exiting.

    Side effects:
        - Prints to stdout.
        - Reads from / writes to ``~/.daily-github-pulse/snapshots.json``
          when ``use_snapshots`` is ``True``.

    Examples:
        >>> # Programmatic usage (results go to stdout)
        >>> find_repo_of_the_day(language="python", top_n=5)

        >>> # Disable velocity tracking
        >>> find_repo_of_the_day(use_snapshots=False)
    """
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
