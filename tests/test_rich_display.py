"""
tests/test_rich_display.py

Unit tests for rich_display.py.

All tests run without a real terminal — Rich output is captured via
Console(file=...) or by inspecting return values directly.
No network access is required.

Run:
    pytest tests/test_rich_display.py -v
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rich_display as rd


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _ts(days_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _capture_console(func, *args, **kwargs) -> str:
    """Run func with a fresh in-memory Console and return captured text."""
    from rich.console import Console
    buf = io.StringIO()
    con = Console(file=buf, highlight=False, no_color=True, width=200)
    # Temporarily replace the module-level console
    original = rd.console
    rd.console = con
    try:
        func(*args, **kwargs)
    finally:
        rd.console = original
    return buf.getvalue()


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture()
def sample_repo() -> dict:
    return {
        "id": 1,
        "full_name": "owner/repo",
        "stargazers_count": 15000,
        "forks_count": 900,
        "language": "Python",
        "description": "A test repository for rich display",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "html_url": "https://github.com/owner/repo",
    }


@pytest.fixture()
def sample_snapshots() -> dict:
    return {
        "owner/repo": {
            "stars": 14800,
            "saved_at": _ts(days_ago=1),
        }
    }


@pytest.fixture()
def sample_user() -> dict:
    return {
        "login": "octocat",
        "name": "The Octocat",
        "company": "@GitHub",
        "location": "San Francisco, CA",
        "bio": "A mysterious developer who loves octopuses and cats.",
        "public_repos": 8,
        "followers": 17000,
        "following": 9,
        "html_url": "https://github.com/octocat",
    }


# ─────────────────────────────────────────────
# RICH_AVAILABLE flag
# ─────────────────────────────────────────────

class TestRichAvailable:
    def test_rich_available_is_bool(self):
        assert isinstance(rd.RICH_AVAILABLE, bool)

    def test_rich_available_is_true_when_rich_installed(self):
        """Rich is in requirements.txt so this should always be True in CI."""
        assert rd.RICH_AVAILABLE is True


# ─────────────────────────────────────────────
# format_velocity_markup
# ─────────────────────────────────────────────

class TestFormatVelocityMarkup:
    def test_none_delta_contains_first_run(self):
        assert "first run" in rd.format_velocity_markup(None)

    def test_none_delta_is_dim_styled(self):
        result = rd.format_velocity_markup(None)
        assert "dim" in result or "yellow" in result

    def test_positive_delta_has_plus_sign(self):
        assert "+200" in rd.format_velocity_markup(200)

    def test_positive_delta_is_green(self):
        assert "green" in rd.format_velocity_markup(200)

    def test_negative_delta_has_minus(self):
        result = rd.format_velocity_markup(-50)
        assert "-50" in result

    def test_negative_delta_is_red(self):
        assert "red" in rd.format_velocity_markup(-50)

    def test_zero_delta_has_no_plus_or_minus_prefix(self):
        result = rd.format_velocity_markup(0)
        assert "+-" not in result
        assert "+0" not in result

    def test_with_velocity_includes_per_day(self):
        result = rd.format_velocity_markup(200, velocity=200.0)
        assert "/day" in result or "day" in result

    def test_without_velocity_no_per_day(self):
        result = rd.format_velocity_markup(200)
        assert "/day" not in result

    def test_large_number_uses_comma(self):
        assert "10,000" in rd.format_velocity_markup(10000)

    def test_returns_string(self):
        assert isinstance(rd.format_velocity_markup(100), str)

    def test_closing_tag_present(self):
        """Rich markup must be balanced."""
        result = rd.format_velocity_markup(100)
        assert "[/" in result


# ─────────────────────────────────────────────
# print_header
# ─────────────────────────────────────────────

class TestPrintHeader:
    def test_repos_mode_label_in_output(self, capsys):
        rd.print_header(since_days=1, mode="repos")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "Trending" in combined or "trending" in combined.lower()

    def test_developers_mode_label_in_output(self, capsys):
        rd.print_header(since_days=7, mode="developers")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "Developer" in combined or "developer" in combined.lower()

    def test_day_count_appears_in_output(self, capsys):
        rd.print_header(since_days=7, mode="repos")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "7" in combined

    def test_singular_day_label(self, capsys):
        rd.print_header(since_days=1, mode="repos")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "day" in combined.lower()

    def test_plural_days_label(self, capsys):
        rd.print_header(since_days=3, mode="repos")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "day" in combined.lower()


# ─────────────────────────────────────────────
# print_repo_table
# ─────────────────────────────────────────────

class TestPrintRepoTable:
    def test_full_name_appears_in_output(self, sample_repo, sample_snapshots):
        output = _capture_console(
            rd.print_repo_table,
            {"Test Category": [sample_repo]},
            sample_snapshots,
        )
        assert "owner/repo" in output

    def test_star_count_appears_in_output(self, sample_repo, sample_snapshots):
        output = _capture_console(
            rd.print_repo_table,
            {"Test Category": [sample_repo]},
            sample_snapshots,
        )
        assert "15,000" in output

    def test_language_appears_in_output(self, sample_repo, sample_snapshots):
        output = _capture_console(
            rd.print_repo_table,
            {"Test Category": [sample_repo]},
            sample_snapshots,
        )
        assert "Python" in output

    def test_description_appears_in_output(self, sample_repo, sample_snapshots):
        output = _capture_console(
            rd.print_repo_table,
            {"Test Category": [sample_repo]},
            sample_snapshots,
        )
        assert "A test repository for rich display" in output

    def test_multiple_repos_all_appear(self, sample_repo, sample_snapshots):
        repo2 = dict(sample_repo)
        repo2["full_name"] = "other/project"
        repo2["id"] = 2
        output = _capture_console(
            rd.print_repo_table,
            {"Test Category": [sample_repo, repo2]},
            sample_snapshots,
        )
        assert "owner/repo" in output
        assert "other/project" in output

    def test_empty_category_does_not_raise(self, sample_snapshots):
        try:
            _capture_console(
                rd.print_repo_table,
                {"Empty": []},
                sample_snapshots,
            )
        except Exception as exc:
            pytest.fail(f"print_repo_table raised on empty category: {exc}")

    def test_multiple_categories_both_rendered(self, sample_repo, sample_snapshots):
        repo2 = dict(sample_repo)
        repo2["full_name"] = "second/repo"
        repo2["id"] = 2
        output = _capture_console(
            rd.print_repo_table,
            {"Category A": [sample_repo], "Category B": [repo2]},
            sample_snapshots,
        )
        assert "owner/repo" in output
        assert "second/repo" in output

    def test_repo_with_no_description_does_not_raise(self, sample_repo, sample_snapshots):
        sample_repo["description"] = None
        try:
            _capture_console(
                rd.print_repo_table,
                {"Test": [sample_repo]},
                sample_snapshots,
            )
        except Exception as exc:
            pytest.fail(f"Raised on None description: {exc}")

    def test_repo_with_no_language_does_not_raise(self, sample_repo, sample_snapshots):
        sample_repo["language"] = None
        try:
            _capture_console(
                rd.print_repo_table,
                {"Test": [sample_repo]},
                sample_snapshots,
            )
        except Exception as exc:
            pytest.fail(f"Raised on None language: {exc}")

    def test_no_snapshot_does_not_raise(self, sample_repo):
        try:
            _capture_console(
                rd.print_repo_table,
                {"Test": [sample_repo]},
                {},
            )
        except Exception as exc:
            pytest.fail(f"Raised with empty snapshots: {exc}")

    def test_rank_numbers_in_output(self, sample_repo, sample_snapshots):
        repo2 = dict(sample_repo)
        repo2["id"] = 2
        repo2["full_name"] = "other/repo"
        output = _capture_console(
            rd.print_repo_table,
            {"Test": [sample_repo, repo2]},
            sample_snapshots,
        )
        assert "1" in output
        assert "2" in output

    def test_updated_date_appears(self, sample_repo, sample_snapshots):
        output = _capture_console(
            rd.print_repo_table,
            {"Test": [sample_repo]},
            sample_snapshots,
        )
        assert "2026-06-01" in output


# ─────────────────────────────────────────────
# print_developer_table
# ─────────────────────────────────────────────

class TestPrintDeveloperTable:
    def test_login_appears_in_output(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "octocat" in output

    def test_name_appears_in_output(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "The Octocat" in output

    def test_follower_count_appears(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "17,000" in output

    def test_location_appears(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "San Francisco" in output

    def test_bio_appears(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "octopuses" in output

    def test_company_stripped_of_at_sign(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "GitHub" in output
        # @ sign should be stripped from company
        assert "@GitHub" not in output

    def test_multiple_developers_all_appear(self, sample_user):
        user2 = dict(sample_user)
        user2["login"] = "torvalds"
        user2["name"] = "Linus Torvalds"
        output = _capture_console(rd.print_developer_table, [sample_user, user2])
        assert "octocat" in output
        assert "torvalds" in output

    def test_empty_list_does_not_raise(self):
        try:
            _capture_console(rd.print_developer_table, [])
        except Exception as exc:
            pytest.fail(f"Raised on empty list: {exc}")

    def test_missing_bio_does_not_raise(self, sample_user):
        sample_user["bio"] = None
        try:
            _capture_console(rd.print_developer_table, [sample_user])
        except Exception as exc:
            pytest.fail(f"Raised on None bio: {exc}")

    def test_missing_location_does_not_raise(self, sample_user):
        sample_user["location"] = None
        try:
            _capture_console(rd.print_developer_table, [sample_user])
        except Exception as exc:
            pytest.fail(f"Raised on None location: {exc}")

    def test_missing_company_does_not_raise(self, sample_user):
        sample_user["company"] = None
        try:
            _capture_console(rd.print_developer_table, [sample_user])
        except Exception as exc:
            pytest.fail(f"Raised on None company: {exc}")

    def test_rank_numbers_in_output(self, sample_user):
        user2 = dict(sample_user)
        user2["login"] = "user2"
        output = _capture_console(rd.print_developer_table, [sample_user, user2])
        assert "1" in output
        assert "2" in output

    def test_repo_count_appears(self, sample_user):
        output = _capture_console(rd.print_developer_table, [sample_user])
        assert "8" in output


# ─────────────────────────────────────────────
# make_ai_filter_progress
# ─────────────────────────────────────────────

class TestMakeAiFilterProgress:
    def test_returns_non_none_when_rich_available(self):
        result = rd.make_ai_filter_progress()
        assert result is not None

    def test_returns_progress_instance(self):
        from rich.progress import Progress
        result = rd.make_ai_filter_progress()
        assert isinstance(result, Progress)

    def test_progress_is_usable_as_context_manager(self):
        prog = rd.make_ai_filter_progress()
        try:
            with prog:
                task = prog.add_task("Testing...", total=3)
                prog.advance(task)
        except Exception as exc:
            pytest.fail(f"Progress context manager raised: {exc}")

    def test_returns_none_when_rich_unavailable(self, monkeypatch):
        monkeypatch.setattr(rd, "RICH_AVAILABLE", False)
        result = rd.make_ai_filter_progress()
        assert result is None
