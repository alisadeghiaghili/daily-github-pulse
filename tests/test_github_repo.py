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
from unittest.mock import MagicMock, call, patch

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


def _mock_user_response(user: dict) -> MagicMock:
    """Build a mock requests.Response returning a single user dict."""
    resp = MagicMock()
    resp.json.return_value = user
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


@pytest.fixture()
def sample_user() -> dict:
    """A minimal enriched user dict that mirrors GitHub Users API shape."""
    return {
        "login": "octocat",
        "id": 583231,
        "name": "The Octocat",
        "company": "@GitHub",
        "location": "San Francisco, CA",
        "bio": "A mysterious developer who loves octopuses and cats.",
        "public_repos": 8,
        "followers": 17000,
        "following": 9,
        "html_url": "https://github.com/octocat",
    }


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
            json.dumps(sample_snapshots, ensure_ascii=False),
            encoding="utf-8",
        )
        result = m.load_snapshots()
        assert result == sample_snapshots


# ──────────────────────────────────────────────
# save_snapshots
# ──────────────────────────────────────────────

class TestSaveSnapshots:
    def _make_repos(self, full_name: str, stars: int) -> dict:
        return {
            "Category": [
                {
                    "full_name": full_name,
                    "stargazers_count": stars,
                    "id": 1,
                }
            ]
        }

    def test_creates_directory_and_file(self, tmp_snapshot_file):
        m.save_snapshots(self._make_repos("owner/repo", 100))
        assert tmp_snapshot_file.exists()

    def test_written_stars_match_repo(self, tmp_snapshot_file):
        m.save_snapshots(self._make_repos("owner/repo", 500))
        data = json.loads(tmp_snapshot_file.read_text(encoding="utf-8"))
        assert data["owner/repo"]["stars"] == 500

    def test_merges_with_existing_data(self, tmp_snapshot_file):
        m.save_snapshots(self._make_repos("owner/alpha", 100))
        m.save_snapshots(self._make_repos("owner/beta", 200))
        data = json.loads(tmp_snapshot_file.read_text(encoding="utf-8"))
        assert "owner/alpha" in data
        assert "owner/beta" in data

    def test_overwrites_existing_entry_for_same_repo(self, tmp_snapshot_file):
        m.save_snapshots(self._make_repos("owner/repo", 100))
        m.save_snapshots(self._make_repos("owner/repo", 999))
        data = json.loads(tmp_snapshot_file.read_text(encoding="utf-8"))
        assert data["owner/repo"]["stars"] == 999


# ──────────────────────────────────────────────
# star_delta
# ──────────────────────────────────────────────

class TestStarDelta:
    def test_returns_none_for_new_repo(self, sample_repo):
        assert m.star_delta(sample_repo, {}) is None

    def test_positive_delta(self, sample_repo, sample_snapshots):
        assert m.star_delta(sample_repo, sample_snapshots) == 142

    def test_zero_delta(self, sample_snapshots):
        repo = {
            "full_name": "owner/repo",
            "stargazers_count": 12400,
        }
        assert m.star_delta(repo, sample_snapshots) == 0

    def test_negative_delta(self, sample_snapshots):
        repo = {
            "full_name": "owner/repo",
            "stargazers_count": 12000,
        }
        assert m.star_delta(repo, sample_snapshots) == -400


# ──────────────────────────────────────────────
# format_velocity
# ──────────────────────────────────────────────

class TestFormatVelocity:
    def test_none_delta_shows_first_run_message(self):
        result = m.format_velocity(None, None)
        assert "first run" in result

    def test_none_velocity_shows_first_run_message(self):
        result = m.format_velocity(None, None)
        assert "first run" in result

    def test_positive_delta_shows_plus_sign(self):
        result = m.format_velocity(142, 71.0)
        assert "+142" in result

    def test_zero_delta(self):
        result = m.format_velocity(0, 0.0)
        assert "⭐" in result

    def test_negative_delta_no_plus_sign(self):
        result = m.format_velocity(-3, -1.5)
        assert "-3" in result
        assert "+-3" not in result

    def test_large_number_uses_comma_separator(self):
        result = m.format_velocity(10000, 5000.0)
        assert "10,000" in result

    def test_velocity_shown_in_output(self):
        result = m.format_velocity(700, 100.0)
        assert "100.0" in result

    def test_output_contains_per_day(self):
        result = m.format_velocity(200, 50.0)
        assert "/day" in result


# ──────────────────────────────────────────────
# format_repo
# ──────────────────────────────────────────────

class TestFormatRepo:
    def test_contains_full_name(self, sample_repo):
        out = m.format_repo(sample_repo, 1, {})
        assert "owner/repo" in out

    def test_contains_rank(self, sample_repo):
        out = m.format_repo(sample_repo, 3, {})
        assert "#3" in out

    def test_contains_star_count(self, sample_repo):
        out = m.format_repo(sample_repo, 1, {})
        assert "12,542" in out

    def test_contains_html_url(self, sample_repo):
        out = m.format_repo(sample_repo, 1, {})
        assert "https://github.com/owner/repo" in out

    def test_no_snapshot_shows_first_run(self, sample_repo):
        out = m.format_repo(sample_repo, 1, {})
        assert "first run" in out

    def test_with_snapshot_shows_delta(self, sample_repo, sample_snapshots):
        out = m.format_repo(sample_repo, 1, sample_snapshots)
        assert "+142" in out

    def test_missing_description_shows_fallback(self, sample_repo):
        sample_repo["description"] = None
        out = m.format_repo(sample_repo, 1, {})
        assert "No description" in out

    def test_missing_language_shows_na(self, sample_repo):
        sample_repo["language"] = None
        out = m.format_repo(sample_repo, 1, {})
        assert "N/A" in out

    def test_description_truncated_to_80_chars(self, sample_repo):
        sample_repo["description"] = "x" * 200
        out = m.format_repo(sample_repo, 1, {})
        assert "x" * 80 in out
        assert "x" * 81 not in out


# ──────────────────────────────────────────────
# parse_boolean_query
# ──────────────────────────────────────────────

class TestParseBooleanQuery:
    def test_plain_term_unchanged(self):
        assert m.parse_boolean_query("LLM") == "LLM"

    def test_and_removed(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert "AND" not in result
        assert "LLM" in result
        assert "agent" in result

    def test_or_preserved(self):
        result = m.parse_boolean_query("LLM OR GPT")
        assert "OR" in result
        assert "LLM" in result
        assert "GPT" in result

    def test_not_becomes_minus(self):
        result = m.parse_boolean_query("agent NOT benchmark")
        assert "-benchmark" in result
        assert "NOT" not in result

    def test_parens_removed(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent")
        assert "(" not in result
        assert ")" not in result

    def test_full_complex_expression(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent AND NOT benchmark")
        assert "OR" in result
        assert "agent" in result
        assert "-benchmark" in result
        assert "AND" not in result
        assert "(" not in result
        assert "NOT" not in result

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            m.parse_boolean_query("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError):
            m.parse_boolean_query("   ")

    def test_no_extra_whitespace_in_output(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert "  " not in result  # no double spaces

    def test_not_with_quoted_phrase(self):
        result = m.parse_boolean_query('agent NOT "code review"')
        assert '-"code review"' in result
        assert "NOT" not in result


# ──────────────────────────────────────────────
# search_trending_repos
# ──────────────────────────────────────────────

class TestSearchTrendingRepos:
    def _repo(self, repo_id: int, name: str) -> dict:
        return {
            "id": repo_id,
            "full_name": name,
            "stargazers_count": 100,
            "forks_count": 10,
            "language": "Python",
            "description": "",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
            "html_url": f"https://github.com/{name}",
        }

    @patch("github_repo_of_the_day.requests.get")
    def test_browse_mode_returns_new_today_and_active_giants(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos()
        assert set(result.keys()) == {"New Today", "Active Giants"}

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_returns_new_relevant_and_active_relevant(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keyword="LLM")
        assert set(result.keys()) == {"New & Relevant", "Active & Relevant"}

    @patch("github_repo_of_the_day.requests.get")
    def test_browse_mode_new_today_uses_stars_gt_10(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        calls = mock_get.call_args_list
        new_today_query = calls[0].kwargs["params"]["q"]
        assert "stars:>10" in new_today_query

    @patch("github_repo_of_the_day.requests.get")
    def test_browse_mode_active_giants_uses_stars_gt_1000(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        calls = mock_get.call_args_list
        active_giants_query = calls[1].kwargs["params"]["q"]
        assert "stars:>1000" in active_giants_query

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_new_relevant_uses_stars_gt_50(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        calls = mock_get.call_args_list
        new_relevant_query = calls[0].kwargs["params"]["q"]
        assert "stars:>50" in new_relevant_query
        assert "stars:>10" not in new_relevant_query

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_active_relevant_uses_stars_gt_500(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        calls = mock_get.call_args_list
        active_relevant_query = calls[1].kwargs["params"]["q"]
        assert "stars:>500" in active_relevant_query
        assert "stars:>1000" not in active_relevant_query

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_preserves_time_dimension(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="MCP", since_days=7)
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "created:>=" in query or "pushed:>=" in query

    @patch("github_repo_of_the_day.requests.get")
    def test_deduplication_across_categories(self, mock_get):
        shared_repo = self._repo(1, "owner/shared")
        mock_get.return_value = _mock_response([shared_repo])
        result = m.search_trending_repos()
        ids = [r["id"] for repos in result.values() for r in repos]
        assert ids.count(1) == 1

    @patch("github_repo_of_the_day.requests.get")
    def test_language_filter_appended_to_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(language="rust")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "language:rust" in query

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_single_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert '"LLM"' in query

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_multi_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert '"LLM agent"' in query

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_includes_in_scope(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="MCP", search_in="name,description")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "in:name,description" in query

    @patch("github_repo_of_the_day.requests.get")
    def test_no_keyword_produces_no_in_qualifier(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert " in:" not in query

    def test_invalid_search_in_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid search_in"):
            m.search_trending_repos(keyword="test", search_in="topics")

    def test_invalid_search_in_error_lists_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            m.search_trending_repos(keyword="test", search_in="xyz,topics")
        msg = str(exc_info.value)
        assert "name" in msg
        assert "description" in msg
        assert "readme" in msg

    def test_valid_search_in_tokens_do_not_raise(self):
        valid_combos = [
            "name",
            "description",
            "readme",
            "name,description",
            "name,readme",
            "description,readme",
            "name,description,readme",
        ]
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([])
            for combo in valid_combos:
                m.search_trending_repos(keyword="test", search_in=combo)

    @patch("github_repo_of_the_day.requests.get")
    def test_http_error_propagates(self, mock_get):
        import requests as req
        mock_get.return_value.raise_for_status.side_effect = req.HTTPError("403")
        with pytest.raises(req.HTTPError):
            m.search_trending_repos()

    @patch("github_repo_of_the_day.requests.get")
    def test_empty_results_per_category(self, mock_get):
        mock_get.return_value = _mock_response([])
        result = m.search_trending_repos()
        for repos in result.values():
            assert repos == []

    # ── Boolean keyword tests ────────────────────────────────────────────

    @patch("github_repo_of_the_day.requests.get")
    def test_boolean_keyword_not_quoted(self, mock_get):
        """Boolean expression must NOT be wrapped in quotes."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM OR GPT")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            # Should contain OR operator, not be a single quoted phrase
            assert "OR" in query
            assert '"LLM OR GPT"' not in query

    @patch("github_repo_of_the_day.requests.get")
    def test_boolean_not_translates_to_minus(self, mock_get):
        """NOT operator in keyword must produce -term in query."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="agent AND NOT benchmark")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "-benchmark" in query

    # ── Multi-keyword tests ──────────────────────────────────────────────

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_and_both_terms_in_query(self, mock_get):
        """keywords=[LLM, agent] with AND op: both terms must appear in query."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "agent"], keyword_op="AND")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert '"LLM"' in query
            assert '"agent"' in query

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_or_uses_or_operator(self, mock_get):
        """keywords=[LLM, GPT] with OR op: query must contain OR."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "GPT"], keyword_op="OR")
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "OR" in query

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_returns_relevant_categories(self, mock_get):
        """Multi-keyword mode must use search-mode category labels."""
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keywords=["LLM", "agent"])
        assert set(result.keys()) == {"New & Relevant", "Active & Relevant"}

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_includes_in_scope(self, mock_get):
        """Multi-keyword query must include in: scope qualifier."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(
            keywords=["LLM", "agent"],
            search_in="name,description",
        )
        for call_args in mock_get.call_args_list:
            query = call_args.kwargs["params"]["q"]
            assert "in:name,description" in query

    def test_invalid_keyword_op_raises_value_error(self):
        """keyword_op outside AND/OR must raise ValueError immediately."""
        with pytest.raises(ValueError, match="keyword_op"):
            m.search_trending_repos(keywords=["LLM"], keyword_op="XOR")
