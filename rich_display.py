#!/usr/bin/env python3
"""
rich_display.py  —  Beautiful terminal output for daily-github-pulse

Drop-in replacement for the plain-text format_* functions.
All public functions mirror the originals but render with Rich.

Public API
──────────
  print_repo_table(repos_by_category, snapshots)    → replaces loop in main()
  print_developer_table(developers)                 → replaces loop in main()
  print_header(since_days, mode)                    → decorative header
  format_velocity_markup(delta, velocity)           → rich markup string

Requires: pip install rich
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.rule import Rule
    from rich.style import Style
    from rich.table import Table
    from rich.text import Text
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    RICH_AVAILABLE = False


console = Console() if RICH_AVAILABLE else None  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _star_delta_text(delta: int | None, velocity: float | None) -> "Text":
    """
    Build a Rich Text object for the star-delta / velocity badge.

    Colour logic:
        green  → positive delta
        red    → negative delta
        yellow → zero or no data
    """
    from rich.text import Text  # local import so module loads even without rich

    if delta is None:
        return Text("— first run", style="dim yellow")

    sign = "+" if delta > 0 else ""
    colour = "green" if delta > 0 else ("red" if delta < 0 else "yellow")
    badge = Text(f"{sign}{delta:,} ⭐", style=colour)

    if velocity is not None:
        badge.append(f"  ~{velocity:,}/day", style=f"bold {colour}")

    return badge


def _language_style(lang: str | None) -> str:
    """Map common language names to a Rich colour."""
    palette = {
        "Python": "yellow",
        "JavaScript": "bright_yellow",
        "TypeScript": "blue",
        "Rust": "red",
        "Go": "cyan",
        "C": "white",
        "C++": "bright_white",
        "Java": "bright_red",
        "Kotlin": "magenta",
        "Swift": "bright_magenta",
        "Ruby": "red",
        "PHP": "blue",
        "Shell": "green",
        "Dockerfile": "bright_cyan",
        "HTML": "bright_red",
        "CSS": "bright_blue",
    }
    return palette.get(lang or "", "white")


# ──────────────────────────────────────────────────────────────────────────────
# Public: markup helper (backwards-compatible with plain-text path)
# ──────────────────────────────────────────────────────────────────────────────

def format_velocity_markup(delta: int | None, velocity: float | None = None) -> str:
    """
    Return a Rich markup string for star delta + velocity.

    Suitable for embedding inside ``[rich markup]`` strings.
    Falls back gracefully when Rich is unavailable.

    Examples:
        >>> format_velocity_markup(None)
        '[dim yellow]— first run[/dim yellow]'
        >>> format_velocity_markup(500, 71.4)
        '[green]+500 ⭐  ~71.4/day[/green]'
    """
    if delta is None:
        return "[dim yellow]— first run[/dim yellow]"
    sign = "+" if delta > 0 else ""
    colour = "green" if delta > 0 else ("red" if delta < 0 else "yellow")
    base = f"[{colour}]{sign}{delta:,} ⭐"
    if velocity is not None:
        base += f"  ~{velocity:,}/day"
    return base + f"[/{colour}]"


# ──────────────────────────────────────────────────────────────────────────────
# Public: header
# ──────────────────────────────────────────────────────────────────────────────

def print_header(since_days: int, mode: str = "repos") -> None:
    """
    Print a decorative header panel.

    Args:
        since_days: Look-back window in days.
        mode:       ``"repos"`` or ``"developers"``.
    """
    if not RICH_AVAILABLE:
        label = "Trending Developers" if mode == "developers" else "Trending Repositories"
        print(f"\n🔍  {label}  (last {since_days} day{'s' if since_days != 1 else ''})\n")
        return

    label = "Trending Developers" if mode == "developers" else "Trending Repositories"
    day_str = f"{since_days} day{'s' if since_days != 1 else ''}"
    console.print()
    console.print(
        Panel(
            f"[bold cyan]🔍  {label}[/bold cyan]  "
            f"[dim]— last {day_str}[/dim]",
            box=box.DOUBLE_EDGE,
            border_style="cyan",
            expand=False,
        )
    )
    console.print()


# ──────────────────────────────────────────────────────────────────────────────
# Public: repository display
# ──────────────────────────────────────────────────────────────────────────────

def print_repo_table(repos_by_category: dict, snapshots: dict) -> None:
    """
    Render all categories of repositories as Rich tables.

    One table per category, with columns:
        #  |  Repository  |  Stars  |  Δ Stars  |  Forks  |  Lang  |  Description

    Args:
        repos_by_category: Output of ``search_trending_repos()``.
        snapshots:         Loaded snapshot data from ``load_snapshots()``.
    """
    if not RICH_AVAILABLE:
        # Graceful degradation: plain text
        for category, repos in repos_by_category.items():
            print(f"\n{'─' * 70}")
            print(f"  {category.upper()}  ({len(repos)} results)")
            print(f"{'─' * 70}\n")
            if not repos:
                print("  (no results)\n")
                continue
            for i, repo in enumerate(repos, start=1):
                _print_repo_plain(repo, i, snapshots)
        return

    from github_repo_of_the_day import star_delta, daily_velocity

    for category, repos in repos_by_category.items():
        console.print(Rule(f"[bold magenta]{category.upper()}  ({len(repos)} results)[/bold magenta]"))
        console.print()

        if not repos:
            console.print("  [dim](no results)[/dim]\n")
            continue

        table = Table(
            box=box.ROUNDED,
            border_style="grey50",
            header_style="bold bright_white on grey23",
            show_lines=True,
            expand=True,
        )

        table.add_column("#",           style="dim",          width=3,  justify="right", no_wrap=True)
        table.add_column("Repository",  style="bold cyan",    min_width=24, no_wrap=False)
        table.add_column("Stars",        style="bright_white", width=9,  justify="right", no_wrap=True)
        table.add_column("Δ Stars",      width=18,             justify="right", no_wrap=True)
        table.add_column("Forks",        style="bright_white", width=8,  justify="right", no_wrap=True)
        table.add_column("Lang",         width=12,             no_wrap=True)
        table.add_column("Description",  min_width=30,         no_wrap=False)

        for i, repo in enumerate(repos, start=1):
            delta    = star_delta(repo, snapshots)
            velocity = daily_velocity(repo, snapshots)
            lang     = repo.get("language") or "N/A"
            desc     = (repo.get("description") or "No description")[:120]
            created  = repo["created_at"][:10]
            updated  = repo["updated_at"][:10]

            # Repository cell: name + URL + dates
            repo_text = Text()
            repo_text.append(repo["full_name"], style="bold cyan link " + repo["html_url"])
            repo_text.append(f"\n{created} → {updated}", style="dim")

            # Language cell with colour
            lang_text = Text(lang, style=_language_style(lang))

            table.add_row(
                str(i),
                repo_text,
                f"{repo['stargazers_count']:,}",
                _star_delta_text(delta, velocity),
                f"{repo['forks_count']:,}",
                lang_text,
                desc,
            )

        console.print(table)
        console.print()


def _print_repo_plain(repo: dict, rank: int, snapshots: dict) -> None:
    """Minimal plain-text fallback for a single repo (no Rich)."""
    from github_repo_of_the_day import star_delta, daily_velocity, format_velocity
    delta    = star_delta(repo, snapshots)
    velocity = daily_velocity(repo, snapshots)
    print(
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


# ──────────────────────────────────────────────────────────────────────────────
# Public: developer display
# ──────────────────────────────────────────────────────────────────────────────

def print_developer_table(developers: list[dict]) -> None:
    """
    Render trending developers as a Rich table.

    Columns:
        #  |  Developer  |  Followers  |  Repos  |  Company  |  Location  |  Bio

    Args:
        developers: Output of ``search_trending_developers()``.
    """
    if not RICH_AVAILABLE:
        from github_repo_of_the_day import format_developer
        for i, user in enumerate(developers, start=1):
            print(format_developer(user, i))
        return

    console.print(Rule("[bold magenta]TRENDING DEVELOPERS[/bold magenta]"))
    console.print()

    if not developers:
        console.print("  [dim](no results)[/dim]\n")
        return

    table = Table(
        box=box.ROUNDED,
        border_style="grey50",
        header_style="bold bright_white on grey23",
        show_lines=True,
        expand=True,
    )

    table.add_column("#",          style="dim",           width=3,  justify="right", no_wrap=True)
    table.add_column("Developer",  style="bold green",    min_width=20, no_wrap=False)
    table.add_column("Followers",  style="bright_white",  width=10, justify="right", no_wrap=True)
    table.add_column("Repos",      style="bright_white",  width=7,  justify="right", no_wrap=True)
    table.add_column("Company",    width=18,              no_wrap=True)
    table.add_column("Location",   width=18,              no_wrap=True)
    table.add_column("Bio",        min_width=30,          no_wrap=False)

    for i, user in enumerate(developers, start=1):
        login    = user.get("login") or ""
        name     = user.get("name") or ""
        company  = (user.get("company") or "").strip().lstrip("@")
        location = user.get("location") or "N/A"
        bio      = (user.get("bio") or "No bio")[:100]
        url      = user.get("html_url") or ""

        # Developer cell: login + real name + URL
        dev_text = Text()
        dev_text.append(login, style="bold green link " + url)
        if name:
            dev_text.append(f"  {name}", style="dim")

        table.add_row(
            str(i),
            dev_text,
            f"{user.get('followers', 0):,}",
            f"{user.get('public_repos', 0):,}",
            company or "—",
            location,
            bio,
        )

    console.print(table)
    console.print()


# ──────────────────────────────────────────────────────────────────────────────
# Public: AI filter progress
# ──────────────────────────────────────────────────────────────────────────────

def make_ai_filter_progress() -> "Progress | None":
    """
    Return a Rich Progress context manager for AI filtering, or None.

    Usage::

        with make_ai_filter_progress() as progress:
            task = progress.add_task("Filtering...", total=total_repos)
            for repo in repos:
                ...process...
                progress.advance(task)
    """
    if not RICH_AVAILABLE:
        return None  # type: ignore[return-value]
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    )
