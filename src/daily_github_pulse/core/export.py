"""Export helpers: row builders, JSON/CSV serialisation, and writers."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

from daily_github_pulse.core.velocity import daily_velocity, star_delta

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

_DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def build_export_row(repo: dict, rank: int, category: str, snapshots: dict) -> dict:
    """
    Build a flat export record from a legacy GitHub repo dict.

    Args:
        repo:      Repo dict from GitHub API.
        rank:      1-based rank within its category.
        category:  Category label.
        snapshots: Loaded snapshot data.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    return {
        "rank": rank,
        "category": category,
        "full_name": repo["full_name"],
        "stars": repo["stargazers_count"],
        "star_delta": star_delta(repo, snapshots),
        "daily_velocity": daily_velocity(repo, snapshots),
        "forks": repo["forks_count"],
        "language": repo.get("language") or "",
        "description": (repo.get("description") or "").replace("\n", " "),
        "created_at": repo["created_at"][:10],
        "updated_at": repo["updated_at"][:10],
        "url": repo["html_url"],
    }


def build_dev_export_row(user: dict, rank: int) -> dict:
    """
    Build a flat export record from an enriched user dict.

    Args:
        user: Enriched user dict.
        rank: 1-based display rank.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    return {
        "rank": rank,
        "login": user.get("login") or "",
        "name": user.get("name") or "",
        "company": (user.get("company") or "").strip().lstrip("@"),
        "location": user.get("location") or "",
        "public_repos": user.get("public_repos") or 0,
        "followers": user.get("followers") or 0,
        "following": user.get("following") or 0,
        "url": user.get("html_url") or "",
    }


def build_forge_export_row(
    repo: Any, rank: int, category: str, snapshots: dict
) -> dict:
    """
    Build an export row from a ``ForgeRepo``.

    Args:
        repo:       Normalized repository from a forge client.
        rank:       1-based rank within the category.
        category:   Category label used by the search path.
        snapshots:  Snapshot mapping from ``load_snapshots()``.

    Returns:
        Dict suitable for JSON/CSV export, including velocity fields.
    """
    return {
        "rank": rank,
        "forge": repo.forge,
        "category": category,
        "full_name": repo.full_name,
        "stars": repo.stars,
        "star_delta": star_delta(repo, snapshots),
        "daily_velocity": daily_velocity(repo, snapshots),
        "forks": repo.forks,
        "language": repo.language or "",
        "description": (repo.description or "").replace("\n", " ")[:200],
        "created_at": repo.created_at[:10],
        "updated_at": repo.updated_at[:10],
        "url": repo.url,
    }


def build_forge_dev_export_row(user: Any, rank: int) -> dict:
    """Build an export row from a ``ForgeUser``."""
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


def export_json(rows: list[dict]) -> str:
    """Serialise export rows to a pretty-printed JSON string."""
    return json.dumps(rows, indent=2, ensure_ascii=False)


def export_csv(rows: list[dict], fieldnames: list[str]) -> str:
    """
    Serialise export rows to a CSV string (utf-8-sig for Excel compat).

    ``None`` values become empty strings. Leading formula characters are
    escaped to mitigate CSV injection.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()

    for row in rows:
        safe_row = {}
        for k, v in row.items():
            if v is None:
                safe_row[k] = ""
            elif isinstance(v, str) and v.startswith(_DANGEROUS_CSV_PREFIXES):
                safe_row[k] = f"'{v}"
            else:
                safe_row[k] = v
        writer.writerow(safe_row)
    return buf.getvalue()


def write_output(content: str, output_file: str | None, fmt: str) -> None:
    """
    Write export content to a file or stdout.

    Args:
        content:     String content to write.
        output_file: File path, or ``None`` to write to stdout.
        fmt:         Format label for the confirmation message.
    """
    if output_file:
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        Path(output_file).write_text(content, encoding=encoding)
        print(f"  Exported {fmt.upper()} → {output_file}", file=sys.stderr)
    else:
        print(content)
