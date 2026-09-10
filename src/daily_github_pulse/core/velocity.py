"""Star-count snapshots and time-normalised velocity metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOT_DIR = Path.home() / ".daily-github-pulse"
SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.json"


def load_snapshots(path: Path | None = None) -> dict:
    """
    Load previously saved star counts from disk.

    Args:
        path: Optional override for the snapshot file location.

    Returns:
        Mapping of repo key → ``{"stars": int, "saved_at": ISO string}``.
        Empty dict if the file does not exist or is corrupted.
    """
    target = path or SNAPSHOT_FILE
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(
    repos_by_category: dict,
    path: Path | None = None,
) -> None:
    """
    Persist current star counts to disk, merging with existing data.

    Args:
        repos_by_category: Category → list of repo dicts or ``ForgeRepo``.
        path: Optional override for the snapshot file location.
    """
    from daily_github_pulse.forges.base import ForgeRepo

    target = path or SNAPSHOT_FILE
    existing = load_snapshots(target)
    now = datetime.now(timezone.utc).isoformat()

    for repos in repos_by_category.values():
        for repo in repos:
            if isinstance(repo, ForgeRepo):
                name = f"{repo.forge}:{repo.full_name}"
                stars = repo.stars
            elif isinstance(repo, dict):
                name = repo["full_name"]
                stars = repo["stargazers_count"]
            else:
                continue
            existing[name] = {"stars": stars, "saved_at": now}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _repo_star_key_and_count(repo: Any) -> tuple[str, int] | None:
    """Return ``(snapshot_key, stars)`` for dict or ForgeRepo payloads."""
    from daily_github_pulse.forges.base import ForgeRepo

    if isinstance(repo, ForgeRepo):
        return f"{repo.forge}:{repo.full_name}", repo.stars
    if isinstance(repo, dict):
        return repo["full_name"], repo["stargazers_count"]
    return None


def star_delta(repo: Any, snapshots: dict) -> int | None:
    """
    Stars gained since the last snapshot (raw, not time-normalised).

    Args:
        repo:      Repo dict from an API, or ``ForgeRepo``.
        snapshots: Loaded snapshot data.

    Returns:
        Integer delta, or ``None`` if no previous snapshot exists.
    """
    resolved = _repo_star_key_and_count(repo)
    if resolved is None:
        return None
    name, stars = resolved
    prev = snapshots.get(name)
    if prev is None:
        return None
    return stars - prev["stars"]


def elapsed_days(snapshots: dict, full_name: str) -> float | None:
    """
    Days elapsed since the snapshot was saved (always > 0 when present).

    Args:
        snapshots:  Loaded snapshot data.
        full_name:  Snapshot key (``owner/repo`` or ``forge:owner/repo``).

    Returns:
        Fractional days, or ``None`` when missing/unparseable.
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


def daily_velocity(repo: Any, snapshots: dict) -> float | None:
    """
    Time-normalised star growth rate in stars per day.

    Args:
        repo:      Repo dict or ``ForgeRepo``.
        snapshots: Loaded snapshot data.

    Returns:
        Stars per day rounded to one decimal, or ``None`` on first run.
    """
    delta = star_delta(repo, snapshots)
    if delta is None:
        return None

    resolved = _repo_star_key_and_count(repo)
    if resolved is None:
        return None
    name, _ = resolved

    days = elapsed_days(snapshots, name)
    if days is None:
        return None
    return round(delta / days, 1)
