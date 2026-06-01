#!/usr/bin/env python3
"""
GitHub #1 Repo of the Day Finder
Fetches trending/top repositories from GitHub based on today's activity.

Token priority:
  1. --token CLI flag
  2. GITHUB_TOKEN in .env file (loaded via python-dotenv)
  3. Unauthenticated (60 req/hr limit)
"""

import os
import requests
from datetime import date, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def get_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def search_trending_repos(language: str = None, since_days: int = 1, top_n: int = 10) -> dict:
    """
    Query GitHub Search API with two strategies:
      - New Today:     repos created recently with >10 stars (fast-rising newcomers)
      - Active Giants: repos pushed today with >1000 stars (established, actively maintained)

    Note: GitHub API has no official trending endpoint. Star velocity (daily gain)
    is not available publicly, so total stars are used as a proxy.

    Args:
        language:   Optional language filter (e.g. "python", "rust")
        since_days: How many days back to look (default: 1 = today)
        top_n:      Max results per category

    Returns:
        dict with category labels as keys and lists of repo dicts as values
    """
    since_date = (date.today() - timedelta(days=since_days)).isoformat()

    queries = {
        "New Today": f"created:>={since_date} stars:>10",
        "Active Giants": f"pushed:>={since_date} stars:>1000",
    }

    if language:
        queries = {k: v + f" language:{language}" for k, v in queries.items()}

    results = {}
    for label, query in queries.items():
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=get_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": top_n},
            timeout=15,
        )
        resp.raise_for_status()
        results[label] = resp.json().get("items", [])

    return results


def format_repo(repo: dict, rank: int) -> str:
    """Format a single repo dict into a human-readable string."""
    return (
        f"{'='*70}\n"
        f"#{rank}  {repo['full_name']}\n"
        f"    Stars: {repo['stargazers_count']:,}  "
        f"Forks: {repo['forks_count']:,}  "
        f"Lang: {repo.get('language') or 'N/A'}\n"
        f"    Created: {repo['created_at'][:10]}  |  Updated: {repo['updated_at'][:10]}\n"
        f"    {(repo.get('description') or 'No description')[:80]}\n"
        f"    {repo['html_url']}\n"
    )


def find_repo_of_the_day(language: str = None, since_days: int = 1, top_n: int = 10):
    """Entry point: fetch and print top repos of the day."""
    print(f"\n{'#'*70}")
    print(f"  GitHub Repo of the Day - {date.today().isoformat()}")
    if language:
        print(f"  Language filter: {language}")
    auth_status = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
    print(f"  {auth_status}")
    print(f"{'#'*70}\n")

    try:
        all_results = search_trending_repos(language=language, since_days=since_days, top_n=top_n)
    except requests.HTTPError as e:
        print(f"GitHub API error: {e}")
        if not GITHUB_TOKEN:
            print("  Add GITHUB_TOKEN to your .env file to increase rate limits.")
        return

    for category, repos in all_results.items():
        print(f"\n{'─'*70}")
        print(f"  {category}")
        print(f"{'─'*70}")
        if not repos:
            print("  No repositories found.\n")
            continue
        for i, repo in enumerate(repos, 1):
            print(format_repo(repo, i))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Find GitHub top repos of the day.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Token setup (recommended):
  Create a .env file in the project root:
    GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
  Then add .env to your .gitignore.
  Get a token: https://github.com/settings/tokens
        """,
    )
    parser.add_argument("--language", "-l", type=str, default=None,
                        help="Filter by language (e.g. python, javascript, rust)")
    parser.add_argument("--days", "-d", type=int, default=1,
                        help="Look back N days (default: 1)")
    parser.add_argument("--top", "-n", type=int, default=10,
                        help="Number of repos per category (default: 10)")
    parser.add_argument("--token", "-t", type=str, default=None,
                        help="GitHub PAT - overrides .env if provided")

    args = parser.parse_args()

    if args.token:
        GITHUB_TOKEN = args.token

    find_repo_of_the_day(language=args.language, since_days=args.days, top_n=args.top)
