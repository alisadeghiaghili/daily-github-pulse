"""CLI application for multi-forge trending search and velocity display."""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from daily_github_pulse import VERSION
from daily_github_pulse.ai.filter import apply_ai_filter, load_ai_filter_config
from daily_github_pulse.core.boolean import (
    BoolNode,
    Term,
    apply_wildcards_to_keywords,
    parse_boolean_query,
)
from daily_github_pulse.core.export import (
    DEV_EXPORT_FIELDS,
    EXPORT_FIELDS,
    build_dev_export_row,
    build_export_row,
    build_forge_dev_export_row,
    build_forge_export_row,
    export_csv,
    export_json,
    write_output,
)
from daily_github_pulse.core.periods import PERIOD_DAYS, resolve_period
from daily_github_pulse.core.velocity import (
    SNAPSHOT_FILE,
    daily_velocity,
    load_snapshots,
    save_snapshots,
    star_delta,
)

try:
    from daily_github_pulse.display.rich import (
        RICH_AVAILABLE,
        print_developer_table,
        print_header,
        print_repo_table,
    )
except ImportError:
    RICH_AVAILABLE = False
    print_header = None
    print_repo_table = None
    print_developer_table = None


def format_velocity(delta: int | None, velocity: float | None = None) -> str:
    """Render star delta and daily velocity as a human-readable badge."""
    if delta is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    if velocity is None:
        return f"  Δ {sign}{delta:,} ⭐"
    return f"  Δ {sign}{delta:,} ⭐ total  |  ~{velocity:,} ⭐/day"


def format_forge_repo(repo, rank: int, snapshots: dict) -> str:
    """Format a ForgeRepo for plain-text display."""
    delta = star_delta(repo, snapshots)
    velocity = daily_velocity(repo, snapshots)
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


def format_forge_user(user, rank: int) -> str:
    """Format a ForgeUser for plain-text display."""
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
    """Search multiple forges in parallel."""
    from daily_github_pulse.forges import get_forge

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

    all_results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(forge_names))) as pool:
        futures = {pool.submit(_search_one, name): name for name in forge_names}
        for future in as_completed(futures):
            forge_name = futures[future]
            try:
                _, results = future.result()
                all_results[forge_name] = results
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠  {forge_name} search failed: {exc}", file=sys.stderr)

    if not all_results:
        print("  ✗  All forge searches failed.", file=sys.stderr)

    return all_results


def merge_forge_results(multi_results: dict[str, dict], top_n: int = 10) -> list:
    """Merge multi-forge results into a single ranked list by stars."""
    all_repos = []
    for categories in multi_results.values():
        for repos in categories.values():
            all_repos.extend(repos)
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
    from daily_github_pulse.forges import get_forge

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
                print(f"  ⚠  {forge_name} developer search failed: {exc}", file=sys.stderr)

    all_users.sort(key=lambda u: u.followers, reverse=True)
    return all_users[:top_n]


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
    )

    parser.add_argument(
        "--forge",
        default="github",
        metavar="FORGES",
        help=(
            "Forge(s) to search. Comma-separated for multi-forge. "
            "Options: github (default), gitlab, gitea, bitbucket."
        ),
    )
    parser.add_argument(
        "--gitea-url",
        default=None,
        metavar="URL",
        help="Base URL for Gitea instances (e.g. https://codeberg.org).",
    )
    parser.add_argument(
        "--developers",
        action="store_true",
        help="Show trending developers instead of repositories.",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=1,
        metavar="N",
        help="Look-back window in days (default: 1). Overridden by --period.",
    )
    parser.add_argument(
        "-p",
        "--period",
        choices=list(PERIOD_DAYS),
        default=None,
        help="Named look-back period: day, week, month.",
    )
    parser.add_argument(
        "-l",
        "--language",
        default=None,
        metavar="LANG",
        help="Filter by programming language (e.g. python, rust, go).",
    )
    parser.add_argument(
        "-n",
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of results per category (default: 10).",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        default=None,
        metavar="TERM",
        help="Single keyword filter (legacy).",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=None,
        metavar="TERM",
        help="One or more keyword terms. Combined with --keyword-op.",
    )
    parser.add_argument(
        "--keyword-op",
        choices=["AND", "OR"],
        default="AND",
        help="Boolean operator for --keywords (default: AND).",
    )
    parser.add_argument(
        "--keyword-not",
        nargs="+",
        default=None,
        metavar="TERM",
        help="Terms to exclude from --keywords search.",
    )
    parser.add_argument(
        "--search-in",
        default="name,description",
        metavar="FIELDS",
        help="Comma-separated fields: name, description, readme.",
    )
    parser.add_argument(
        "--bool-query",
        default=None,
        metavar="EXPR",
        help="Boolean keyword expression, e.g. '(LLM OR GPT) AND agent'.",
    )
    parser.add_argument(
        "--wildcard",
        action="store_true",
        help="Expand ? and * wildcards in --keywords against the NLTK corpus.",
    )
    parser.add_argument(
        "--ai-filter",
        action="store_true",
        help="Enable LLM-based relevance filtering.",
    )
    parser.add_argument(
        "--ai-filter-query",
        default=None,
        metavar="QUERY",
        help="Natural-language description of what you're looking for.",
    )
    parser.add_argument(
        "--ai-filter-fallback",
        choices=["fail", "passthrough"],
        default="fail",
        help="Behaviour when the LLM is unavailable (default: fail).",
    )
    parser.add_argument(
        "--token",
        default=None,
        metavar="TOKEN",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--gitlab-token",
        default=None,
        metavar="TOKEN",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--gitea-token",
        default=None,
        metavar="TOKEN",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "-f",
        "--output-file",
        default=None,
        metavar="PATH",
        help="Write output to this file instead of stdout.",
    )
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip saving star counts for velocity tracking this run.",
    )
    parser.add_argument(
        "--clear-snapshots",
        action="store_true",
        help="Delete all stored snapshots and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return parser


def main() -> None:
    """Parse CLI arguments and run the requested search."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.clear_snapshots:
        if SNAPSHOT_FILE.exists():
            SNAPSHOT_FILE.unlink()
            print("  ✓  Snapshots cleared.", file=sys.stderr)
        else:
            print("  (no snapshots to clear)", file=sys.stderr)
        return

    try:
        since_days = resolve_period(args.period, args.days)
    except ValueError as exc:
        parser.error(str(exc))

    forge_names = [f.strip().lower() for f in args.forge.split(",") if f.strip()]
    if not forge_names:
        parser.error("--forge requires at least one forge name.")

    if args.token and "github" in forge_names:
        print(
            "WARNING: --token is deprecated and may leak via process listings; "
            "set GITHUB_TOKEN in the environment instead.",
            file=sys.stderr,
        )
        os.environ["GITHUB_TOKEN"] = args.token
    if args.gitlab_token:
        print(
            "WARNING: --gitlab-token is deprecated and may leak via process listings; "
            "set GITLAB_TOKEN in the environment instead.",
            file=sys.stderr,
        )
        os.environ["GITLAB_TOKEN"] = args.gitlab_token
    if args.gitea_token:
        print(
            "WARNING: --gitea-token is deprecated and may leak via process listings; "
            "set GITEA_TOKEN in the environment instead.",
            file=sys.stderr,
        )
        os.environ["GITEA_TOKEN"] = args.gitea_token

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
            from daily_github_pulse.forges import get_forge

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
            rows = [
                build_forge_dev_export_row(u, i)
                for i, u in enumerate(developers, start=1)
            ]
            if args.output == "json":
                write_output(export_json(rows), args.output_file, "json")
            else:
                write_output(
                    export_csv(rows, ["rank", "forge"] + DEV_EXPORT_FIELDS[1:]),
                    args.output_file,
                    "csv",
                )
        return

    if RICH_AVAILABLE and print_header:
        print_header(since_days, mode="repos")
    else:
        print(
            f"\n🔍  Trending Repositories  "
            f"(last {since_days} day{'s' if since_days != 1 else ''})\n",
            file=sys.stderr,
        )

    bool_query_ast = None
    if args.bool_query:
        try:
            bool_query_ast = parse_boolean_query(args.bool_query)
        except ValueError as exc:
            parser.error(str(exc))

    effective_keywords = args.keywords
    if args.wildcard and effective_keywords:
        effective_keywords = apply_wildcards_to_keywords(effective_keywords)

    if len(forge_names) == 1:
        from daily_github_pulse.forges import get_forge

        client = get_forge(forge_names[0])
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
        merged = merge_forge_results(multi_results, top_n=args.top)
        repos_by_category = {"All Forges": merged}

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
                f'      Query: "{ai_query}"\n',
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

    snapshots = load_snapshots()

    if args.output == "text":
        if RICH_AVAILABLE and print_repo_table:
            print_repo_table(repos_by_category, snapshots)
        else:
            from daily_github_pulse.forges.base import ForgeRepo as _ForgeRepo

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
        from daily_github_pulse.forges.base import ForgeRepo as _ForgeRepo

        all_rows = []
        for category, repos in repos_by_category.items():
            for i, repo in enumerate(repos, start=1):
                if isinstance(repo, _ForgeRepo):
                    all_rows.append(
                        build_forge_export_row(repo, i, category, snapshots)
                    )
                else:
                    all_rows.append(build_export_row(repo, i, category, snapshots))

        export_fields = ["rank", "forge"] + [f for f in EXPORT_FIELDS if f != "rank"]
        if args.output == "json":
            write_output(export_json(all_rows), args.output_file, "json")
        else:
            write_output(export_csv(all_rows, export_fields), args.output_file, "csv")

    if not args.no_snapshot:
        try:
            save_snapshots(repos_by_category, prune=True)
        except OSError as exc:
            print(f"  ⚠  Could not save snapshots: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
