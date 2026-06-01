#!/usr/bin/env python3
"""
daily-github-pulse  v1.6.0
──────────────────────────
Discover GitHub's top repositories and trending developers of the day.

How velocity works
──────────────────
On each run, star counts are saved to a local snapshot file:
  ~/.daily-github-pulse/snapshots.json

Each snapshot entry stores:
  - stars     : star count at save time
  - saved_at  : UTC ISO timestamp of the save

On the next run two velocity numbers are computed:

  star_delta      — raw difference (current − snapshot), regardless of
                    how much time has passed between runs.

  daily_velocity  — time-normalised rate: star_delta / elapsed_days.
                    This is the number that stays meaningful even if you
                    haven't run the tool for two weeks.
                    Rounded to one decimal place.
                    None when no previous snapshot exists (first run).

Modes
─────
  repos       — show trending repositories only (default)
  developers  — show trending developers only
  both        — show repositories then developers

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
from datetime import date, datetime, timedelta, timezone
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
VERSION = "1.6.0"
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
    "daily_velocity",
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
        dict mapping repo full_name → {"stars": int, "saved_at": ISO string}.
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
    now = datetime.now(timezone.utc).isoformat()

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
    Calculate stars gained since the last snapshot (raw, not time-normalised).

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


def elapsed_days(snapshots: dict, full_name: str) -> float | None:
    """
    Return the number of days elapsed since the snapshot was saved.

    Parses the ``saved_at`` ISO timestamp stored in the snapshot entry and
    computes the difference against the current UTC time.

    Args:
        snapshots:  loaded snapshot data (from ``load_snapshots()``).
        full_name:  repository full name, e.g. ``"owner/repo"``.

    Returns:
        Elapsed time in fractional days (always > 0), or ``None`` if the
        repo has no snapshot entry or the ``saved_at`` field is missing /
        unparseable.

    Examples:
        >>> import json
        >>> from datetime import datetime, timezone, timedelta
        >>> ts = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        >>> snaps = {"owner/repo": {"stars": 100, "saved_at": ts}}
        >>> days = elapsed_days(snaps, "owner/repo")
        >>> 0.4 < days < 0.6  # roughly 0.5 day
        True
    """
    entry = snapshots.get(full_name)
    if entry is None:
        return None
    saved_at_raw = entry.get("saved_at")
    if not saved_at_raw:
        return None
    try:
        saved_dt = datetime.fromisoformat(saved_at_raw)
        if saved_dt.tzinfo is None:
            saved_dt = saved_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_seconds = (now - saved_dt).total_seconds()
        return max(delta_seconds / 86400, 1 / 86400)
    except (ValueError, TypeError):
        return None


def daily_velocity(repo: dict, snapshots: dict) -> float | None:
    """
    Compute the time-normalised star growth rate in stars per day.

    Unlike ``star_delta()``, this value stays meaningful regardless of how
    long ago the snapshot was taken.  A repo that gained 1 400 stars over
    14 days reports a ``daily_velocity`` of 100.0, the same as a repo that
    gained 100 stars today.

    Args:
        repo:      repo dict from GitHub API.
        snapshots: loaded snapshot data.

    Returns:
        Stars per day rounded to one decimal place, or ``None`` when no
        previous snapshot exists for this repo (first run).

    Examples:
        >>> import json
        >>> from datetime import datetime, timezone, timedelta
        >>> ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        >>> snaps = {"owner/repo": {"stars": 12400, "saved_at": ts}}
        >>> repo = {"full_name": "owner/repo", "stargazers_count": 13100}
        >>> daily_velocity(repo, snaps)
        100.0
    """
    delta = star_delta(repo, snapshots)
    if delta is None:
        return None
    days = elapsed_days(snapshots, repo["full_name"])
    if days is None:
        return None
    return round(delta / days, 1)


# ──────────────────────────────────────────────
# Core search — repositories
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
# Core search — developers
# ──────────────────────────────────────────────
def search_trending_developers(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
) -> dict:
    """
    Query the GitHub Search API and return trending developers by category.

    Uses two complementary strategies since GitHub has no official trending
    endpoint for users:

    - New Voices    — accounts created recently with >50 followers (rising stars).
    - Prolific Today — accounts that pushed today with >500 followers (active veterans).

    Users appearing in both result sets are deduplicated — shown only in
    the first category that returns them.

    Note: the ``language`` filter is applied via ``language:X`` qualifier
    on the user search endpoint, which matches users whose most-used
    language is X.  This is a best-effort approximation.

    Args:
        language:   Optional language filter (e.g. "python", "rust").
        since_days: Days to look back (default: 1).
        top_n:      Max results per category; GitHub hard limit is 100.

    Returns:
        dict: {category_label: [user_dict, ...]}
        Each user_dict contains at minimum:
            login, id, html_url, avatar_url, type,
            and (for user-type results) followers, public_repos,
            created_at fetched from the Users API.

    Raises:
        requests.HTTPError, requests.ConnectionError, requests.Timeout
    """
    since_date = (date.today() - timedelta(days=since_days)).isoformat()

    queries = {
        "New Voices":     f"type:user created:>={since_date} followers:>50",
        "Prolific Today": f"type:user followers:>500",
    }
    if language:
        queries = {k: v + f" language:{language}" for k, v in queries.items()}

    results: dict = {}
    seen_ids: set = set()

    for label, query in queries.items():
        resp = requests.get(
            "https://api.github.com/search/users",
            headers=get_headers(),
            params={"q": query, "sort": "followers", "order": "desc", "per_page": top_n},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        enriched: list[dict] = []
        for user in items:
            if user["id"] in seen_ids:
                continue
            seen_ids.add(user["id"])
            # Fetch full profile to get followers / public_repos / created_at
            try:
                profile_resp = requests.get(
                    f"https://api.github.com/users/{user['login']}",
                    headers=get_headers(),
                    timeout=10,
                )
                profile_resp.raise_for_status()
                profile = profile_resp.json()
                user["followers"]     = profile.get("followers", 0)
                user["public_repos"]  = profile.get("public_repos", 0)
                user["created_at"]    = profile.get("created_at", "")
                user["bio"]           = profile.get("bio") or ""
                user["name"]          = profile.get("name") or user["login"]
                user["blog"]          = profile.get("blog") or ""
                user["company"]       = profile.get("company") or ""
            except (requests.HTTPError, requests.Timeout):
                # Partial data is better than skipping the user entirely
                user.setdefault("followers", 0)
                user.setdefault("public_repos", 0)
                user.setdefault("created_at", "")
                user.setdefault("bio", "")
                user.setdefault("name", user["login"])
                user.setdefault("blog", "")
                user.setdefault("company", "")
            enriched.append(user)

        results[label] = enriched

    return results


# ──────────────────────────────────────────────
# Export helpers
# ──────────────────────────────────────────────
def build_export_row(repo: dict, rank: int, category: str, snapshots: dict) -> dict:
    """
    Build a flat export record from a repo dict.

    Extracts and renames the fields defined in EXPORT_FIELDS.
    ``star_delta`` and ``daily_velocity`` are ``null`` / empty string on
    the first run (no previous snapshot exists).

    Args:
        repo:      repo dict from GitHub API.
        rank:      1-based rank within its category.
        category:  category label (e.g. "New Today").
        snapshots: loaded snapshot data.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    delta = star_delta(repo, snapshots)
    velocity = daily_velocity(repo, snapshots)
    return {
        "rank":           rank,
        "category":       category,
        "full_name":      repo["full_name"],
        "stars":          repo["stargazers_count"],
        "star_delta":     delta,
        "daily_velocity": velocity,
        "forks":          repo["forks_count"],
        "language":       repo.get("language") or "",
        "description":    (repo.get("description") or "").replace("\n", " "),
        "created_at":     repo["created_at"][:10],
        "updated_at":     repo["updated_at"][:10],
        "url":            repo["html_url"],
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

    ``None`` values (star_delta / daily_velocity on first run) are written
    as empty strings.

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
def format_velocity(delta: int | None, velocity: float | None) -> str:
    """
    Render star delta and daily velocity as a human-readable badge.

    Args:
        delta:    Raw star delta from ``star_delta()``.
        velocity: Stars-per-day from ``daily_velocity()``.

    Returns:
        Single-line string starting with two spaces.

    Examples:
        >>> format_velocity(None, None)
        '  Δ  — (first run — no velocity data yet)'
        >>> format_velocity(700, 100.0)
        '  Δ +700 ⭐ total  |  ~100.0 ⭐/day'
        >>> format_velocity(0, 0.0)
        '  Δ 0 ⭐ total  |  ~0.0 ⭐/day'
    """
    if delta is None or velocity is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    return f"  Δ {sign}{delta:,} ⭐ total  |  ~{velocity:,} ⭐/day"


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
    velocity = daily_velocity(repo, snapshots)
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {repo['full_name']}\n"
        f"    Stars: {repo['stargazers_count']:,}  "
        f"Forks: {repo['forks_count']:,}  "
        f"Lang: {repo.get('language') or 'N/A'}\n"
        f"{format_velocity(delta, velocity)}\n"
        f"    Created: {repo['created_at'][:10]}  |  Updated: {repo['updated_at'][:10]}\n"
        f"    {(repo.get('description') or 'No description')[:80]}\n"
        f"    {repo['html_url']}\n"
    )


def format_developer(user: dict, rank: int) -> str:
    """
    Format a single developer dict into a human-readable terminal block.

    Args:
        user: enriched user dict from search_trending_developers().
              Expected keys: login, name, followers, public_repos,
              created_at, bio, company, blog, html_url.
        rank: 1-based display rank within its category.

    Returns:
        Multi-line string ending with a trailing newline.

    Examples:
        >>> user = {
        ...     "login": "octocat", "name": "The Octocat",
        ...     "followers": 10000, "public_repos": 8,
        ...     "created_at": "2011-01-25T18:44:36Z",
        ...     "bio": "How people build software.",
        ...     "company": "@github", "blog": "https://github.blog",
        ...     "html_url": "https://github.com/octocat",
        ... }
        >>> out = format_developer(user, 1)
        >>> "#1" in out and "octocat" in out
        True
    """
    joined = user.get("created_at", "")[:10] or "unknown"
    company = f"  @ {user['company']}" if user.get("company") else ""
    blog    = f"  🔗 {user['blog']}"  if user.get("blog")    else ""
    bio_line = f"    {user['bio'][:80]}\n" if user.get("bio") else ""
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {user['login']}  ({user.get('name', user['login'])})\n"
        f"    Followers: {user.get('followers', 0):,}  "
        f"Repos: {user.get('public_repos', 0):,}  "
        f"Joined: {joined}{company}\n"
        f"{bio_line}"
        f"{blog}\n" if blog else ""
        f"    {user['html_url']}\n"
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def find_pulse(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    dev_top_n: int = 10,
    keyword: str | None = None,
    search_in: str = "name,description",
    use_snapshots: bool = True,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
    mode: Literal["repos", "developers", "both"] = "repos",
) -> None:
    """
    Fetch, display/export trending repositories and/or developers.

    Orchestration order:
      1. Print session header (text mode only).
      2. Load previous snapshot (if use_snapshots and mode includes repos).
      3. Fetch repos and/or developers via search functions.
      4. Render output in the requested format.
      5. Save new snapshot baseline (if use_snapshots and repos were fetched).

    Args:
        language:      Language filter. Default: None (all languages).
        since_days:    Days to look back. Default: 1.
        top_n:         Repos per category. Default: 10.
        dev_top_n:     Developers per category. Default: 10.
        keyword:       Keyword filter (repos only). Default: None.
        search_in:     Search scope for keyword. Default: "name,description".
        use_snapshots: Load/save velocity snapshots. Default: True.
        output_fmt:    Output format: "text" (default), "json", or "csv".
        output_file:   Write output to this file path instead of stdout.
        mode:          What to fetch: "repos", "developers", or "both".

    Returns:
        None

    Raises:
        SystemExit(1): On GitHub API errors.
    """
    show_repos = mode in ("repos", "both")
    show_devs  = mode in ("developers", "both")

    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        if language:
            print(f"  Language : {language}")
        if keyword and show_repos:
            print(f"  Keyword  : '{keyword}'  in [{search_in}]")
        auth = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
        print(f"  Auth     : {auth}")
        if show_repos:
            snap_status = "enabled" if use_snapshots else "disabled (--no-snapshot)"
            print(f"  Velocity : {snap_status}")
        print(f"  Mode     : {mode}")
        print(f"{'#' * 70}\n")

    snapshots = load_snapshots() if (use_snapshots and show_repos) else {}

    # ── Repositories ──────────────────────────
    all_repos: dict = {}
    if show_repos:
        try:
            all_repos = search_trending_repos(
                language=language,
                since_days=since_days,
                top_n=top_n,
                keyword=keyword,
                search_in=search_in,
            )
        except requests.HTTPError as exc:
            print(f"[ERROR] GitHub API returned: {exc}", file=sys.stderr)
            if not GITHUB_TOKEN:
                print("  Tip: set GITHUB_TOKEN in .env to raise rate limit.",
                      file=sys.stderr)
            sys.exit(1)
        except requests.ConnectionError:
            print("[ERROR] Could not reach GitHub API. Check your internet connection.",
                  file=sys.stderr)
            sys.exit(1)
        except requests.Timeout:
            print("[ERROR] GitHub API request timed out.", file=sys.stderr)
            sys.exit(1)

    # ── Developers ────────────────────────────
    all_devs: dict = {}
    if show_devs:
        try:
            all_devs = search_trending_developers(
                language=language,
                since_days=since_days,
                top_n=dev_top_n,
            )
        except requests.HTTPError as exc:
            print(f"[ERROR] GitHub API (users) returned: {exc}", file=sys.stderr)
            sys.exit(1)
        except requests.ConnectionError:
            print("[ERROR] Could not reach GitHub API. Check your internet connection.",
                  file=sys.stderr)
            sys.exit(1)
        except requests.Timeout:
            print("[ERROR] GitHub API request timed out.", file=sys.stderr)
            sys.exit(1)

    # ── Render ────────────────────────────────
    if output_fmt == "text":
        if show_repos:
            for category, repos in all_repos.items():
                print(f"\n{'─' * 70}")
                print(f"  📦 Repositories — {category}")
                print(f"{'─' * 70}")
                if not repos:
                    print("  No repositories found.\n")
                    continue
                for i, repo in enumerate(repos, 1):
                    print(format_repo(repo, i, snapshots))

        if show_devs:
            for category, devs in all_devs.items():
                print(f"\n{'─' * 70}")
                print(f"  👤 Developers — {category}")
                print(f"{'─' * 70}")
                if not devs:
                    print("  No developers found.\n")
                    continue
                for i, dev in enumerate(devs, 1):
                    print(format_developer(dev, i))
    else:
        rows: list[dict] = []
        for category, repos in all_repos.items():
            for i, repo in enumerate(repos, 1):
                rows.append(build_export_row(repo, i, category, snapshots))
        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows), output_file, "csv")

    if use_snapshots and show_repos:
        save_snapshots(all_repos)
        if output_fmt == "text":
            print(f"\n  Snapshot saved → {SNAPSHOT_FILE}")
        else:
            print(f"  Snapshot saved → {SNAPSHOT_FILE}", file=sys.stderr)


# backward-compat alias
find_repo_of_the_day = find_pulse


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="daily-github-pulse",
        description="Find GitHub trending repos and developers — with real star velocity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: today's top repos, all languages
  python github_repo_of_the_day.py

  # Trending developers only
  python github_repo_of_the_day.py --mode developers

  # Both repos and developers
  python github_repo_of_the_day.py --mode both

  # Trending Python developers
  python github_repo_of_the_day.py --mode developers --language python

  # Named period shortcut (day / week / month)
  python github_repo_of_the_day.py --period week
  python github_repo_of_the_day.py --period month --language rust

  # Export as JSON to stdout
  python github_repo_of_the_day.py --output json

  # Export as CSV to a file
  python github_repo_of_the_day.py --output csv --output-file results.csv

  # Search by keyword
  python github_repo_of_the_day.py --keyword "LLM agent" --output json

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
    parser.add_argument("--dev-top", type=int, default=10, metavar="N",
                        help="Developers per category (default: 10)")
    parser.add_argument("--token", "-t", metavar="TOKEN",
                        help="GitHub PAT — overrides .env")
    parser.add_argument("--keyword", "-k", metavar="WORD",
                        help="Keyword to search repos (e.g. 'LLM agent')")
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
        "--mode", "-m",
        choices=["repos", "developers", "both"],
        default="repos",
        metavar="MODE",
        help="What to fetch: repos (default), developers, both",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Disable snapshot 