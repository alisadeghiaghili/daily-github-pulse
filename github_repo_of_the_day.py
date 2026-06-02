#!/usr/bin/env python3
"""
daily-github-pulse  v1.6.0
──────────────────────────
Discover GitHub's top repositories AND developers of the day — with real star velocity.

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

Token priority
──────────────
  1. --token CLI flag
  2. GITHUB_TOKEN environment variable / .env file
  3. Unauthenticated  →  60 req/hr limit
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import os
import re
import string
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

# Valid tokens for search_in parameter
VALID_SEARCH_IN_TOKENS = {"name", "description", "readme"}

# Maximum number of wildcard expansions allowed per term
WILDCARD_MAX_EXPANSIONS = 20

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

# Fields included in developer JSON / CSV exports (in order)
DEV_EXPORT_FIELDS = [
    "rank",
    "login",
    "name",
    "company",
    "location",
    "public_repos",
    "followers",
    "following",
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

    Args:
        period: Named period string or None.
        days:   Numeric fallback.

    Returns:
        Resolved number of look-back days.

    Raises:
        ValueError: If period is not a recognised token.

    Examples:
        >>> resolve_period("week", 1)
        7
        >>> resolve_period(None, 3)
        3
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
# Wildcard expansion
# ──────────────────────────────────────────────
def expand_wildcards(
    term: str,
    max_expansions: int = WILDCARD_MAX_EXPANSIONS,
) -> str:
    """
    Expand a single term containing ``?`` wildcards into a GitHub Search
    OR expression.

    Each ``?`` is replaced by every letter a–z in turn, producing all
    combinations.  The result is wrapped in an OR expression so GitHub
    Search treats it as any of the expansions.

    GitHub Search does not support wildcards natively, so client-side
    expansion is the only viable approach.  Expansion is intentionally
    capped at ``max_expansions`` to keep queries usable; exceeding the
    cap raises ``ValueError`` rather than silently sending a 2 000-term
    query.

    Args:
        term:           A single search token that may contain one or
                        more ``?`` characters, e.g. ``"analy?e"``.
        max_expansions: Hard cap on the number of generated variants.
                        Default: ``WILDCARD_MAX_EXPANSIONS`` (20).

    Returns:
        If ``term`` contains no ``?``, returns ``term`` unchanged.
        If expansion produces exactly one variant, returns that variant.
        Otherwise returns ``"variant1 OR variant2 OR ..."``, with each
        multi-word variant quoted.

    Raises:
        ValueError: If the number of expansions exceeds ``max_expansions``.
        ValueError: If ``term`` is empty or whitespace-only.

    Examples:
        >>> expand_wildcards("analy?e")
        'analyse OR analyze'
        >>> expand_wildcards("color?")
        'colora OR colorb OR colorc OR ... OR colorz'
        >>> expand_wildcards("agent")   # no wildcard
        'agent'
        >>> expand_wildcards("t??t")    # 676 combos — raises
        Traceback (most recent call last):
            ...
        ValueError: Wildcard expansion of 't??t' would produce 676 variants ...
    """
    if not term or not term.strip():
        raise ValueError("Term must not be empty.")

    if "?" not in term:
        return term

    # Count wildcards and compute total expansion size
    n_wildcards = term.count("?")
    total = 26 ** n_wildcards
    if total > max_expansions:
        raise ValueError(
            f"Wildcard expansion of '{term}' would produce {total} variants "
            f"(max allowed: {max_expansions}). "
            f"Use fewer '?' or a more specific pattern."
        )

    # Split term into fixed parts around each '?'
    parts = term.split("?")
    # Generate all combinations of n_wildcards letters
    variants = [
        "".join(
            part + ch
            for part, ch in itertools.zip_longest(parts[:-1], combo, fillvalue="")
        ) + parts[-1]
        for combo in itertools.product(string.ascii_lowercase, repeat=n_wildcards)
    ]

    if len(variants) == 1:
        return variants[0]

    return " OR ".join(variants)


# ──────────────────────────────────────────────
# Boolean keyword parser
# ──────────────────────────────────────────────
def parse_boolean_query(expr: str) -> str:
    """
    Translate a human-readable boolean expression to GitHub Search syntax.
    Wildcards (``?``) in individual terms are expanded via
    ``expand_wildcards()`` before boolean translation.

    Transformation rules applied in order:
      1. Parentheses are stripped (unsupported by GitHub Search).
      2. Each token containing ``?`` is expanded via ``expand_wildcards()``.
      3. ``NOT <term>`` or ``NOT "phrase"`` → ``-term`` / ``-"phrase"``.
      4. ``AND`` (explicit) → removed; adjacent terms are implicit AND.
      5. ``OR`` → kept as-is (native GitHub operator).
      6. Excess whitespace is collapsed.

    Args:
        expr: Boolean expression string, optionally containing wildcards.

    Returns:
        GitHub Search query fragment.

    Raises:
        ValueError: If ``expr`` is empty, or a wildcard term exceeds
                    ``WILDCARD_MAX_EXPANSIONS``.

    Examples:
        >>> parse_boolean_query('LLM AND agent')
        'LLM agent'
        >>> parse_boolean_query('analy?e AND agent')
        'analyse OR analyze agent'
        >>> parse_boolean_query('(LLM OR GPT) AND agent AND NOT benchmark')
        'LLM OR GPT agent -benchmark'
    """
    if not expr or not expr.strip():
        raise ValueError("Boolean expression must not be empty.")

    s = expr.strip()

    # 1. Remove parentheses
    s = s.replace("(", " ").replace(")", " ")

    # 2. Expand wildcards in each token (skip quoted phrases and operators)
    def _maybe_expand(token: str) -> str:
        """Expand token if it contains '?' and is not a boolean operator."""
        if token.upper() in ("AND", "OR", "NOT") or token.startswith('"'):
            return token
        if "?" in token:
            return expand_wildcards(token)
        return token

    # Tokenise preserving quoted phrases, then expand bare tokens with ?
    # Pattern: quoted phrase OR non-whitespace token
    tokens = re.findall(r'"[^"]+"|\S+', s)
    tokens = [_maybe_expand(t) for t in tokens]
    s = " ".join(tokens)

    # 3. NOT <term> → -term  (handles both "NOT word" and "NOT \"phrase\"")
    s = re.sub(r'\bNOT\s+("[^"]+"|\S+)', lambda m: f"-{m.group(1)}", s)

    # 4. Remove explicit AND
    s = re.sub(r'\bAND\b', ' ', s)

    # 5. Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    return s


# ──────────────────────────────────────────────
# Snapshot helpers
# ──────────────────────────────────────────────
def load_snapshots() -> dict:
    if not SNAPSHOT_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(repos_by_category: dict) -> None:
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
    prev = snapshots.get(repo["full_name"])
    if prev is None:
        return None
    return repo["stargazers_count"] - prev["stars"]


def elapsed_days(snapshots: dict, full_name: str) -> float | None:
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
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    search_in: str = "name,description",
) -> dict:
    """
    Query the GitHub Search API and return top repositories by category.

    Browse mode (no keyword/keywords):
      - New Today     — recently created repos with >10 stars.
      - Active Giants — recently pushed repos with >1000 stars.

    Search mode (keyword or keywords provided):
      - New & Relevant    — recently created repos with >50 stars.
      - Active & Relevant — recently pushed repos with >500 stars.

    Keyword resolution priority:
      1. ``keywords`` list → joined with ``keyword_op``.
      2. ``keyword`` with boolean operators / wildcards → parsed via
         ``parse_boolean_query()`` (which calls ``expand_wildcards()``).
      3. Plain ``keyword`` → quoted as exact phrase.

    Args:
        language:    Optional language filter.
        since_days:  Days to look back (default: 1).
        top_n:       Max results per category.
        keyword:     Single keyword, phrase, boolean expression, or
                     wildcard pattern (e.g. ``"analy?e AND agent"``).
        keywords:    List of keywords for multi-keyword mode.
        keyword_op:  Operator joining ``keywords`` list: "AND" or "OR".
        search_in:   Comma-separated search scope.
                     Valid tokens: "name", "description", "readme".

    Returns:
        dict: {category_label: [repo_dict, ...]}

    Raises:
        ValueError: If search_in contains invalid tokens, keyword_op is
                    invalid, or a wildcard pattern exceeds max expansions.
        requests.HTTPError, requests.ConnectionError, requests.Timeout
    """
    # Validate keyword_op
    op_upper = keyword_op.strip().upper()
    if op_upper not in ("AND", "OR"):
        raise ValueError(
            f"Invalid keyword_op '{keyword_op}'. Valid options: AND, OR"
        )

    # Validate search_in tokens
    tokens = {t.strip() for t in search_in.split(",") if t.strip()}
    invalid = tokens - VALID_SEARCH_IN_TOKENS
    if invalid:
        raise ValueError(
            f"Invalid search_in token(s): {', '.join(sorted(invalid))}. "
            f"Valid options: {', '.join(sorted(VALID_SEARCH_IN_TOKENS))}"
        )

    since_date = (date.today() - timedelta(days=since_days)).isoformat()

    # ── Build keyword qualifier ──────────────────────────────────────────
    keyword_qualifier = ""

    if keywords and len(keywords) > 0:
        # Multi-keyword mode: each term may contain wildcards
        expanded = []
        for k in keywords:
            expanded.append(expand_wildcards(k) if "?" in k else f'"{k}"')
        if op_upper == "OR":
            joined = " OR ".join(expanded)
        else:
            joined = " ".join(expanded)
        keyword_qualifier = f" {joined} in:{search_in}"

    elif keyword:
        _BOOL_PATTERN = re.compile(r'\b(AND|OR|NOT)\b|[()\?]')
        if _BOOL_PATTERN.search(keyword):
            # Boolean expression or wildcard — parse (expand_wildcards called inside)
            parsed = parse_boolean_query(keyword)
            keyword_qualifier = f" {parsed} in:{search_in}"
        else:
            # Plain keyword / phrase — wrap in quotes
            keyword_qualifier = f" \"{keyword}\" in:{search_in}"

    # ── Build queries by category ────────────────────────────────────────
    if keyword_qualifier:
        queries = {
            "New & Relevant":    f"created:>={since_date} stars:>50{keyword_qualifier}",
            "Active & Relevant": f"pushed:>={since_date} stars:>500{keyword_qualifier}",
        }
    else:
        queries = {
            "New Today":     f"created:>={since_date} stars:>10",
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
) -> list[dict]:
    since_date = (date.today() - timedelta(days=since_days)).isoformat()
    lang_qualifier = f" language:{language}" if language else ""

    queries = [
        f"created:>={since_date} repos:>0 followers:>0{lang_qualifier}",
        f"followers:>100{lang_qualifier}",
    ]

    seen_logins: set = set()
    raw_users: list = []

    for query in queries:
        if len(raw_users) >= top_n:
            break
        resp = requests.get(
            "https://api.github.com/search/users",
            headers=get_headers(),
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


# ──────────────────────────────────────────────
# Export helpers
# ──────────────────────────────────────────────
def build_export_row(repo: dict, rank: int, category: str, snapshots: dict) -> dict:
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


def build_dev_export_row(user: dict, rank: int) -> dict:
    return {
        "rank":         rank,
        "login":        user.get("login") or "",
        "name":         user.get("name") or "",
        "company":      (user.get("company") or "").strip().lstrip("@"),
        "location":     user.get("location") or "",
        "public_repos": user.get("public_repos") or 0,
        "followers":    user.get("followers") or 0,
        "following":    user.get("following") or 0,
        "url":          user.get("html_url") or "",
    }


def export_json(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False)


def export_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()


def write_output(content: str, output_file: str | None, fmt: str) -> None:
    if output_file:
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        Path(output_file).write_text(content, encoding=encoding)
        print(f"  Exported {fmt.upper()} → {output_file}", file=sys.stderr)
    else:
        print(content)


# ──────────────────────────────────────────────
# Text formatting
# ──────────────────────────────────────────────
def format_velocity(delta: int | None, velocity: float | None) -> str:
    """
    Render star delta and daily velocity as a human-readable badge.

    Examples:
        >>> format_velocity(None, None)
        '  Δ  — (first run — no velocity data yet)'
        >>> format_velocity(700, 100.0)
        '  Δ +700 ⭐ total  |  ~100.0 ⭐/day'
    """
    if delta is None or velocity is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    return f"  Δ {sign}{delta:,} ⭐ total  |  ~{velocity:,} ⭐/day"


def format_repo(repo: dict, rank: int, snapshots: dict) -> str:
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
    name = user.get("name") or user.get("login", "")
    company = (user.get("company") or "").strip().lstrip("@")
    location = user.get("location") or "N/A"
    bio = (user.get("bio") or "No bio")[:80]
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {user.get('login', '')}  ({name})\n"
        f"    Followers: {user.get('followers', 0):,}  "
        f"Repos: {user.get('public_repos', 0):,}  "
        f"Following: {user.get('following', 0):,}\n"
        f"    Company : {company or 'N/A'}\n"
        f"    Location: {location}\n"
        f"    {bio}\n"
        f"    {user.get('html_url', '')}\n"
    )


# ──────────────────────────────────────────────
# Entry point — repositories
# ──────────────────────────────────────────────
def find_repo_of_the_day(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    search_in: str = "name,description",
    use_snapshots: bool = True,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
) -> None:
    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        if language:
            print(f"  Language : {language}")
        if keywords:
            print(f"  Keywords : {keywords}  op=[{keyword_op}]  in=[{search_in}]")
        elif keyword:
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
            keywords=keywords,
            keyword_op=keyword_op,
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
        rows: list[dict] = []
        for category, repos in all_results.items():
            for i, repo in enumerate(repos, 1):
                rows.append(build_export_row(repo, i, category, snapshots))
        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows, EXPORT_FIELDS), output_file, "csv")

    if use_snapshots:
        save_snapshots(all_results)
        if output_fmt == "text":
            print(f"\n  Snapshot saved → {SNAPSHOT_FILE}")
        else:
            print(f"  Snapshot saved → {SNAPSHOT_FILE}", file=sys.stderr)


# ──────────────────────────────────────────────
# Entry point — developers
# ──────────────────────────────────────────────
def find_developer_of_the_day(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
) -> None:
    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        print(f"  Mode     : Trending Developers")
        if language:
            print(f"  Language : {language}")
        auth = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
        print(f"  Auth     : {auth}")
        print(f"{'#' * 70}\n")

    try:
        developers = search_trending_developers(
            language=language, since_days=since_days, top_n=top_n
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

    if output_fmt == "text":
        print(f"\n{'─' * 70}")
        print(f"  Trending Developers")
        print(f"{'─' * 70}")
        if not developers:
            print("  No developers found.\n")
        else:
            for i, user in enumerate(developers, 1):
                print(format_developer(user, i))
    else:
        rows = [build_dev_export_row(u, i) for i, u in enumerate(developers, 1)]
        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows, DEV_EXPORT_FIELDS), output_file, "csv")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="daily-github-pulse",
        description="Find GitHub top repos and developers of the day.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: today's top repos
  python github_repo_of_the_day.py

  # Trending developers
  python github_repo_of_the_day.py --developers

  # Single keyword
  python github_repo_of_the_day.py --keyword "LLM agent"

  # Multi-keyword AND
  python github_repo_of_the_day.py --keyword LLM --keyword agent

  # Multi-keyword OR
  python github_repo_of_the_day.py --keyword LLM --keyword GPT --keyword-op OR

  # Boolean expression
  python github_repo_of_the_day.py --keyword '(LLM OR GPT) AND agent AND NOT benchmark'

  # Wildcard
  python github_repo_of_the_day.py --keyword 'analy?e'

  # Wildcard in boolean
  python github_repo_of_the_day.py --keyword 'analy?e AND agent'

  # Export CSV
  python github_repo_of_the_day.py --output csv --output-file results.csv
        """,
    )

    parser.add_argument("--developers", "--devs", action="store_true")
    parser.add_argument("--language", "-l", metavar="LANG")
    parser.add_argument("--period", "-p", choices=["day", "week", "month"], metavar="PERIOD")
    parser.add_argument("--days", "-d", type=int, default=1, metavar="N")
    parser.add_argument("--top", "-n", type=int, default=10, metavar="N")
    parser.add_argument("--token", "-t", metavar="TOKEN")
    parser.add_argument(
        "--keyword", "-k",
        metavar="WORD",
        action="append",
        dest="keywords",
        help=(
            "Keyword, boolean expression, or wildcard pattern. "
            "Repeat for multi-keyword: --keyword LLM --keyword agent. "
            "Wildcard: --keyword 'analy?e'. "
            "Boolean: --keyword '(LLM OR GPT) AND agent AND NOT benchmark'."
        ),
    )
    parser.add_argument(
        "--keyword-op",
        choices=["AND", "OR"],
        default="AND",
        metavar="OP",
        help="Operator joining multiple --keyword values: AND (default) or OR.",
    )
    parser.add_argument("--search-in", "-s", default="name,description", metavar="SCOPE")
    parser.add_argument("--output", "-o", choices=["text", "json", "csv"], default="text", metavar="FORMAT")
    parser.add_argument("--output-file", "-f", metavar="FILE")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument(
        "--clear-snapshots", action="store_true",
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

    raw_keywords: list[str] | None = args.keywords
    if raw_keywords and len(raw_keywords) == 1:
        kw_single: str | None = raw_keywords[0]
        kw_list: list[str] | None = None
    else:
        kw_single = None
        kw_list = raw_keywords

    if args.developers:
        find_developer_of_the_day(
            language=args.language,
            since_days=effective_days,
            top_n=args.top,
            output_fmt=args.output,
            output_file=args.output_file,
        )
    else:
        find_repo_of_the_day(
            language=args.language,
            since_days=effective_days,
            top_n=args.top,
            keyword=kw_single,
            keywords=kw_list,
            keyword_op=args.keyword_op,
            search_in=args.search_in,
            use_snapshots=not args.no_snapshot,
            output_fmt=args.output,
            output_file=args.output_file,
        )
