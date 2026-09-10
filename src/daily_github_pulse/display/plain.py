"""Plain-text formatters used when Rich is unavailable."""

from __future__ import annotations

from typing import Any

from daily_github_pulse.core.velocity import daily_velocity, star_delta


def format_velocity(delta: int | None, velocity: float | None = None) -> str:
    """
    Render star delta and daily velocity as a human-readable badge.

    Examples:
        >>> format_velocity(None, None)
        '  Δ  — (first run — no velocity data yet)'
        >>> format_velocity(700, 100.0)
        '  Δ +700 ⭐ total  |  ~100.0 ⭐/day'
    """
    if delta is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    if velocity is None:
        return f"  Δ {sign}{delta:,} ⭐"
    return f"  Δ {sign}{delta:,} ⭐ total  |  ~{velocity:,} ⭐/day"


def format_repo(repo: dict, rank: int, snapshots: dict) -> str:
    """Format a single legacy repo dict into a terminal block."""
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
    """Format a single enriched user dict into a terminal block."""
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
