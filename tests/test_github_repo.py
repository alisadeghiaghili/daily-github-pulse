"""
Test suite for daily-github-pulse.

Covers all public functions in github_repo_of_the_day.py.
All GitHub API calls are mocked — no network access required.

Run:
    pytest tests/ -v
    pytest tests/ -v --tb=short   # compact tracebacks
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import github_repo_of_the_day as m


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _ts(days_ago: float = 0) -> str:
    """Return a UTC ISO timestamp N days in the past."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _mock_response(items: list) -> MagicMock:
    """Build a mock requests.Response returning ``items``."""
    resp = MagicMock()
    resp.json.return_value = {"items": items}
    resp.raise_for_status.return_value = None
    return resp


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture()
def sample_repo() -> dict:
    """A minimal repo dict that mirrors GitHub Search API shape."""
    return {
        "id": 1,
        "full_name": "owner/repo",
        "stargazers_count": 12542,
        "forks_count": 834,
        "language": "Python",
        "description": "A test repository",
        "created_at": "2025-03-10T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "html_url": "https://github.com/owner/repo",
    }


@pytest.fixture()
def sample_snapshots() -> dict:
    """Snapshot taken exactly 2 days ago with 12 400 stars."""
    return {
        "owner/repo": {
            "stars": 12400,
            "saved_at": _ts(days_ago=2),
        }
    }


@pytest.fixture()
def tmp_snapshot_file(tmp_path, monkeypatch) -> Path:
    """
    Redirect SNAPSHOT_DIR and SNAPSHOT_FILE to a temp directory so tests
    never touch the real ~/.daily-github-pulse/ folder.
    """
    snap_dir = tmp_path / ".daily-github-pulse"
    snap_file = snap_dir / "snapshots.json"
    monkeypatch.setattr(m, "SNAPSHOT_DIR", snap_dir)
    monkeypatch.setattr(m, "SNAPSHOT_FILE", snap_file)
    return snap_file


# ──────────────────────────────────────────────
# get_headers
# ──────────────────────────────────────────────

class TestGetHeaders:
    def test_no_token_omits_authorization(self, monkeypatch):
        monkeypatch.setattr(m, "GITHUB_TOKEN", None)
        headers = m.get_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github+json"

    def test_with_token_includes_bearer(self, monkeypatch):
        monkeypatch.setattr(m, "GITHUB_TOKEN", "ghp_test123")
        headers = m.get_headers()
        assert headers["Authorization"] == "Bearer ghp_test123"

    def test_accept_header_always_present(self, monkeypatch):
        for token in (None, "ghp_x"):
            monkeypatch.setattr(m, "GITHUB_TOKEN", token)
            assert "Accept" in m.get_headers()


# ──────────────────────────────────────────────
# resolve_period
# ──────────────────────────────────────────────

class TestResolvePeriod:
    def test_day_returns_1(self):
        assert m.resolve_period("day", 99) == 1

    def test_week_returns_7(self):
        assert m.resolve_period("week", 99) == 7

    def test_month_returns_30(self):
        assert m.resolve_period("month", 99) == 30

    def test_none_returns_days_argument(self):
        assert m.resolve_period(None, 14) == 14

    def test_none_returns_default_days(self):
        assert m.resolve_period(None, 1) == 1

    def test_period_takes_precedence_over_days(self):
        assert m.resolve_period("week", 999) == 7

    def test_case_insensitive_upper(self):
        assert m.resolve_period("WEEK", 1) == 7

    def test_case_insensitive_mixed(self):
        assert m.resolve_period("Month", 1) == 30

    def test_whitespace_stripped(self):
        assert m.resolve_period("  day  ", 1) == 1

    def test_invalid_period_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown period"):
            m.resolve_period("yesterday", 1)

    def test_invalid_period_message_lists_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            m.resolve_period("quarterly", 1)
        msg = str(exc_info.value)
        assert "day" in msg
        assert "week" in msg
        assert "month" in msg

    def test_all_valid_period_tokens(self):
        expected = {"day": 1, "week": 7, "month": 30}
        for period, days in expected.items():
            assert m.resolve_period(period, 0) == days


# ──────────────────────────────────────────────
# load_snapshots
# ──────────────────────────────────────────────

class TestLoadSnapshots:
    def test_returns_empty_dict_when_file_missing(self, tmp_snapshot_file):
        assert m.load_snapshots() == {}

    def test_returns_empty_dict_on_corrupt_json(self, tmp_snapshot_file):
        tmp_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_snapshot_file.write_text("not valid json", encoding="utf-8")
        assert m.load_snapshots() == {}

    def test_loads_valid_snapshot_file(self, tmp_snapshot_file, sample_snapshots):
        tmp_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_snapshot_file.write_text(
            json.dumps(sample_snapshots), encoding="utf-8"
        )
        result = m.load_snapshots()
        assert result["owner/repo"]["stars"] == 12400


# ──────────────────────────────────────────────
# save_snapshots
# ──────────────────────────────────────────────

class TestSaveSnapshots:
    def test_creates_directory_and_file(self, tmp_snapshot_file, sample_repo):
        m.save_snapshots({"New Today": [sample_repo]})
        assert tmp_snapshot_file.exists()

    def test_written_stars_match_repo(self, tmp_snapshot_file, sample_repo):
        m.save_snapshots({"New Today": [sample_repo]})
        data = json.loads(tmp_snapshot_file.read_text())
        assert data["owner/repo"]["stars"] == 12542

    def test_saved_at_is_utc_iso_string(self, tmp_snapshot_file, sample_repo):
        m.save_snapshots({"New Today": [sample_repo]})
        data = json.loads(tmp_snapshot_file.read_text())
        saved_at = data["owner/repo"]["saved_at"]
        # Must be parseable and timezone-aware
        dt = datetime.fromisoformat(saved_at)
        assert dt.tzinfo is not None

    def test_merges_with_existing_data(self, tmp_snapshot_file):
        existing = {"other/repo": {"stars": 999, "saved_at": _ts(1)}}
        tmp_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_snapshot_file.write_text(json.dumps(existing), encoding="utf-8")
        new_repo = {"full_name": "owner/new", "stargazers_count": 50}
        m.save_snapshots({"New Today": [new_repo]})
        data = json.loads(tmp_snapshot_file.read_text())
        assert "other/repo" in data
        assert "owner/new" in data

    def test_overwrites_existing_entry_for_same_repo(self, tmp_snapshot_file, sample_repo):
        m.save_snapshots({"New Today": [sample_repo]})
        updated = {**sample_repo, "stargazers_count": 99999}
        m.save_snapshots({"Active Giants": [updated]})
        data = json.loads(tmp_snapshot_file.read_text())
        assert data["owner/repo"]["stars"] == 99999


# ──────────────────────────────────────────────
# star_delta
# ──────────────────────────────────────────────

class TestStarDelta:
    def test_returns_none_for_new_repo(self, sample_repo):
        assert m.star_delta(sample_repo, {}) is None

    def test_positive_delta(self, sample_repo, sample_snapshots):
        # snapshot: 12400 stars 2 days ago; current: 12542 → delta = 142
        assert m.star_delta(sample_repo, sample_snapshots) == 142

    def test_zero_delta(self, sample_repo, sample_snapshots):
        repo = {**sample_repo, "stargazers_count": 12400}
        assert m.star_delta(repo, sample_snapshots) == 0

    def test_negative_delta(self, sample_repo, sample_snapshots):
        repo = {**sample_repo, "stargazers_count": 12397}
        assert m.star_delta(repo, sample_snapshots) == -3


# ──────────────────────────────────────────────
# elapsed_days
# ──────────────────────────────────────────────

class TestElapsedDays:
    def test_returns_none_for_missing_repo(self):
        assert m.elapsed_days({}, "owner/repo") is None

    def test_returns_none_for_missing_saved_at(self):
        snaps = {"owner/repo": {"stars": 100}}
        assert m.elapsed_days(snaps, "owner/repo") is None

    def test_returns_none_for_invalid_timestamp(self):
        snaps = {"owner/repo": {"stars": 100, "saved_at": "not-a-date"}}
        assert m.elapsed_days(snaps, "owner/repo") is None

    def test_approximately_one_day(self):
        snaps = {"owner/repo": {"stars": 100, "saved_at": _ts(days_ago=1)}}
        result = m.elapsed_days(snaps, "owner/repo")
        assert result is not None
        assert 0.99 < result < 1.01

    def test_approximately_seven_days(self):
        snaps = {"owner/repo": {"stars": 100, "saved_at": _ts(days_ago=7)}}
        result = m.elapsed_days(snaps, "owner/repo")
        assert result is not None
        assert 6.99 < result < 7.01

    def test_naive_utc_timestamp_treated_as_utc(self):
        # Old snapshots written before v1.5.0 have no timezone info
        naive_ts = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        snaps = {"owner/repo": {"stars": 100, "saved_at": naive_ts}}
        result = m.elapsed_days(snaps, "owner/repo")
        assert result is not None
        assert 2.99 < result < 3.01

    def test_same_second_save_does_not_return_zero(self):
        # Guard: minimum is 1/86400 (one second), never 0
        snaps = {"owner/repo": {"stars": 100, "saved_at": _ts(days_ago=0)}}
        result = m.elapsed_days(snaps, "owner/repo")
        assert result is not None
        assert result > 0


# ──────────────────────────────────────────────
# daily_velocity
# ──────────────────────────────────────────────

class TestDailyVelocity:
    def test_returns_none_when_no_snapshot(self, sample_repo):
        assert m.daily_velocity(sample_repo, {}) is None

    def test_velocity_over_two_days(self, sample_repo, sample_snapshots):
        # delta=142, elapsed≈2 days → velocity ≈ 71.0
        result = m.daily_velocity(sample_repo, sample_snapshots)
        assert result is not None
        assert 70.0 < result < 72.0

    def test_velocity_one_week(self, sample_repo):
        snaps = {"owner/repo": {"stars": 12400, "saved_at": _ts(days_ago=7)}}
        # delta=142 over 7 days → ≈20.3
        result = m.daily_velocity(sample_repo, snaps)
        assert result is not None
        assert 20.0 < result < 21.0

    def test_velocity_normalised_regardless_of_gap(self, sample_repo):
        """Same delta over different gaps must produce different velocities."""
        snaps_short = {"owner/repo": {"stars": 12400, "saved_at": _ts(days_ago=1)}}
        snaps_long  = {"owner/repo": {"stars": 12400, "saved_at": _ts(days_ago=14)}}
        v_short = m.daily_velocity(sample_repo, snaps_short)
        v_long  = m.daily_velocity(sample_repo, snaps_long)
        assert v_short is not None and v_long is not None
        assert v_short > v_long

    def test_zero_delta_gives_zero_velocity(self, sample_repo):
        snaps = {"owner/repo": {"stars": 12542, "saved_at": _ts(days_ago=1)}}
        assert m.daily_velocity(sample_repo, snaps) == 0.0

    def test_negative_velocity(self, sample_repo):
        snaps = {"owner/repo": {"stars": 13000, "saved_at": _ts(days_ago=1)}}
        result = m.daily_velocity(sample_repo, snaps)
        assert result is not None
        assert result < 0

    def test_result_is_rounded_to_one_decimal(self, sample_repo):
        snaps = {"owner/repo": {"stars": 12400, "saved_at": _ts(days_ago=3)}}
        result = m.daily_velocity(sample_repo, snaps)
        assert result is not None
        assert result == round(result, 1)


# ──────────────────────────────────────────────
# format_velocity
# ──────────────────────────────────────────────

class TestFormatVelocity:
    def test_none_shows_first_run_message(self):
        result = m.format_velocity(None, None)
        assert "first run" in result
        assert "Δ" in result

    def test_none_delta_only_shows_first_run(self):
        result = m.format_velocity(None, 42.0)
        assert "first run" in result

    def test_positive_delta_shows_plus_sign(self):
        result = m.format_velocity(142, 71.0)
        assert "+142" in result
        assert "⭐" in result

    def test_shows_daily_velocity(self):
        result = m.format_velocity(142, 71.0)
        assert "71.0" in result
        assert "⭐/day" in result

    def test_zero_delta(self):
        result = m.format_velocity(0, 0.0)
        assert "⭐" in result
        assert "+" not in result

    def test_negative_delta_no_plus_sign(self):
        result = m.format_velocity(-3, -1.5)
        assert "-3" in result
        assert "+" not in result

    def test_large_number_uses_comma_separator(self):
        result = m.format_velocity(10000, 1000.0)
        assert "10,000" in result

    def test_shows_total_label(self):
        result = m.format_velocity(100, 50.0)
        assert "total" in result


# ──────────────────────────────────────────────
# format_repo
# ──────────────────────────────────────────────

class TestFormatRepo:
    def test_contains_full_name(self, sample_repo):
        output = m.format_repo(sample_repo, 1, {})
        assert "owner/repo" in output

    def test_contains_rank(self, sample_repo):
        output = m.format_repo(sample_repo, 3, {})
        assert "#3" in output

    def test_contains_star_count(self, sample_repo):
        output = m.format_repo(sample_repo, 1, {})
        assert "12,542" in output

    def test_contains_html_url(self, sample_repo):
        output = m.format_repo(sample_repo, 1, {})
        assert "https://github.com/owner/repo" in output

    def test_no_snapshot_shows_first_run(self, sample_repo):
        output = m.format_repo(sample_repo, 1, {})
        assert "first run" in output

    def test_with_snapshot_shows_delta_and_velocity(self, sample_repo, sample_snapshots):
        output = m.format_repo(sample_repo, 1, sample_snapshots)
        assert "+142" in output
        assert "⭐/day" in output

    def test_missing_description_shows_fallback(self, sample_repo):
        sample_repo["description"] = None
        output = m.format_repo(sample_repo, 1, {})
        assert "No description" in output

    def test_missing_language_shows_na(self, sample_repo):
        sample_repo["language"] = None
        output = m.format_repo(sample_repo, 1, {})
        assert "N/A" in output

    def test_description_truncated_to_80_chars(self, sample_repo):
        sample_repo["description"] = "x" * 120
        output = m.format_repo(sample_repo, 1, {})
        assert "x" * 80 in output
        assert "x" * 81 not in output


# ──────────────────────────────────────────────
# search_trending_repos
# ──────────────────────────────────────────────

class TestSearchTrendingRepos:
    def test_returns_two_categories(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            result = m.search_trending_repos()
        assert set(result.keys()) == {"New Today", "Active Giants"}

    def test_deduplication_across_categories(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            result = m.search_trending_repos()
        all_ids = [repo["id"] for repos in result.values() for repo in repos]
        assert all_ids.count(sample_repo["id"]) == 1

    def test_language_filter_appended_to_query(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            m.search_trending_repos(language="python")
        for call in mock_get.call_args_list:
            q = call.kwargs["params"]["q"]
            assert "language:python" in q

    def test_keyword_appended_to_query(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            m.search_trending_repos(keyword="LLM agent", search_in="name,description")
        for call in mock_get.call_args_list:
            q = call.kwargs["params"]["q"]
            assert "LLM agent" in q
            assert "in:name,description" in q

    def test_http_error_propagates(self):
        import requests as req
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = req.HTTPError("403")
            mock_get.return_value = mock_resp
            with pytest.raises(req.HTTPError):
                m.search_trending_repos()

    def test_empty_results_per_category(self):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            result = m.search_trending_repos()
        assert result["New Today"] == []
        assert result["Active Giants"] == []
