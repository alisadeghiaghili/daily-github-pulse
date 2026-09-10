"""
Stage 0 stability tests.

Guards the multi-forge entry point against regressions that broke the
public CLI surface:

- ``VERSION`` must be bound after a successful legacy import.
- Forge-aware display/export must resolve snapshot keys as ``forge:full_name``.
- The AI relevance filter must accept both dict and ``ForgeRepo`` inputs.

All network and LLM calls are mocked.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import daily_github_pulse as pulse
import github_repo_of_the_day as legacy
from daily_github_pulse.cli import (
    _build_arg_parser,
    build_forge_export_row,
    format_forge_repo,
)
from forges.base import ForgeRepo


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture()
def forge_repo() -> ForgeRepo:
    return ForgeRepo(
        forge="github",
        id="1",
        full_name="owner/repo",
        stars=150,
        forks=10,
        language="Python",
        description="Test repo",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2026-06-01T00:00:00Z",
        url="https://github.com/owner/repo",
    )


@pytest.fixture()
def forge_snapshots() -> dict:
    """Snapshot keyed the way ``save_snapshots`` persists ForgeRepo entries."""
    return {
        "github:owner/repo": {
            "stars": 100,
            "saved_at": _iso_days_ago(2),
        }
    }


class TestVersionBinding:
    def test_version_is_defined(self):
        assert hasattr(pulse, "VERSION")
        assert pulse.VERSION == legacy.VERSION

    def test_arg_parser_builds_without_nameerror(self):
        parser = _build_arg_parser()
        assert parser.prog == "daily_github_pulse"


class TestForgeVelocityDisplay:
    def test_star_delta_uses_forge_prefix(self, forge_repo, forge_snapshots):
        assert legacy.star_delta(forge_repo, forge_snapshots) == 50

    def test_daily_velocity_non_zero(self, forge_repo, forge_snapshots):
        velocity = legacy.daily_velocity(forge_repo, forge_snapshots)
        assert velocity is not None
        assert velocity == pytest.approx(25.0, rel=0.1)

    def test_format_forge_repo_includes_velocity(self, forge_repo, forge_snapshots):
        text = format_forge_repo(forge_repo, rank=1, snapshots=forge_snapshots)
        assert "owner/repo" in text
        assert "[GITHUB]" in text
        assert "first run" not in text.lower()
        assert "+50" in text

    def test_build_forge_export_row_velocity(self, forge_repo, forge_snapshots):
        row = build_forge_export_row(
            forge_repo, rank=1, category="New Today", snapshots=forge_snapshots
        )
        assert row["forge"] == "github"
        assert row["star_delta"] == 50
        assert row["daily_velocity"] is not None

    def test_legacy_dict_path_still_works(self, forge_snapshots):
        repo = {
            "full_name": "owner/other",
            "stargazers_count": 200,
            "forks_count": 5,
            "language": "Go",
            "description": "legacy",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
            "html_url": "https://github.com/owner/other",
        }
        snaps = {"owner/other": {"stars": 180, "saved_at": _iso_days_ago(1)}}
        assert legacy.star_delta(repo, snaps) == 20


class TestRepoFieldAdapter:
    def test_normalize_dict_repo(self):
        repo = {"full_name": "a/b", "description": "hello"}
        full_name, description = legacy.repo_identity(repo)
        assert full_name == "a/b"
        assert description == "hello"

    def test_normalize_forge_repo(self, forge_repo):
        full_name, description = legacy.repo_identity(forge_repo)
        assert full_name == "owner/repo"
        assert description == "Test repo"

    def test_normalize_missing_description_dict(self):
        full_name, description = legacy.repo_identity({"full_name": "x/y"})
        assert full_name == "x/y"
        assert description == ""


class TestAIFilterForgeRepo:
    def test_is_repo_relevant_accepts_forge_repo(self, forge_repo):
        config = legacy.AIFilterConfig(
            provider="openai",
            base_url="https://api.example/v1",
            model="test-model",
            api_key="k",
        )
        with patch(
            "daily_github_pulse.ai.filter.fetch_readme_snippet",
            return_value="readme text",
        ), patch(
            "daily_github_pulse.ai.filter.call_openai_compatible",
            return_value="YES: matches intent",
        ):
            relevant, reason = legacy.is_repo_relevant(forge_repo, "inference", config)
        assert relevant is True
        assert "matches" in reason

    def test_apply_ai_filter_keeps_relevant_forge_repos(self, forge_repo):
        config = legacy.AIFilterConfig(api_key="k")
        repos_by_category = {"All Forges": [forge_repo]}
        with patch(
            "daily_github_pulse.ai.filter.fetch_readme_snippet", return_value=""
        ), patch(
            "daily_github_pulse.ai.filter.call_openai_compatible",
            return_value="YES: ok",
        ):
            result = legacy.apply_ai_filter(
                repos_by_category,
                query="python tools",
                config=config,
                verbose=False,
            )
        assert result["All Forges"] == [forge_repo]

    def test_apply_ai_filter_drops_irrelevant_forge_repos(self, forge_repo):
        config = legacy.AIFilterConfig(api_key="k")
        repos_by_category = {"All Forges": [forge_repo]}
        with patch(
            "daily_github_pulse.ai.filter.fetch_readme_snippet", return_value=""
        ), patch(
            "daily_github_pulse.ai.filter.call_openai_compatible",
            return_value="NO: unrelated",
        ):
            result = legacy.apply_ai_filter(
                repos_by_category,
                query="quantum",
                config=config,
                verbose=False,
            )
        assert result["All Forges"] == []
