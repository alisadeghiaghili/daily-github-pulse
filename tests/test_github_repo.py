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
        repo = {"full_name": "owner/repo", "stargazers_count": 12400}
        assert m.star_delta(repo, sample_snapshots) == 0

    def test_negative_delta(self, sample_snapshots):
        repo = {"full_name": "owner/repo", "stargazers_count": 12000}
        assert m.star_delta(repo, sample_snapshots) == -400


# ──────────────────────────────────────────────
# format_velocity
# ──────────────────────────────────────────────

class TestFormatVelocity:
    def test_none_shows_first_run_message(self):
        assert "first run" in m.format_velocity(None)

    def test_positive_delta_shows_plus_sign(self):
        assert "+142" in m.format_velocity(142)

    def test_zero_delta(self):
        assert "\u2b50" in m.format_velocity(0)

    def test_negative_delta_no_plus_sign(self):
        result = m.format_velocity(-3)
        assert "-3" in result
        assert "+-3" not in result

    def test_large_number_uses_comma_separator(self):
        assert "10,000" in m.format_velocity(10000)


# ──────────────────────────────────────────────
# format_repo
# ──────────────────────────────────────────────

class TestFormatRepo:
    def test_contains_full_name(self, sample_repo):
        assert "owner/repo" in m.format_repo(sample_repo, 1, {})

    def test_contains_rank(self, sample_repo):
        assert "#3" in m.format_repo(sample_repo, 3, {})

    def test_contains_star_count(self, sample_repo):
        assert "12,542" in m.format_repo(sample_repo, 1, {})

    def test_contains_html_url(self, sample_repo):
        assert "https://github.com/owner/repo" in m.format_repo(sample_repo, 1, {})

    def test_no_snapshot_shows_first_run(self, sample_repo):
        assert "first run" in m.format_repo(sample_repo, 1, {})

    def test_with_snapshot_shows_delta(self, sample_repo, sample_snapshots):
        assert "+142" in m.format_repo(sample_repo, 1, sample_snapshots)

    def test_missing_description_shows_fallback(self, sample_repo):
        sample_repo["description"] = None
        assert "No description" in m.format_repo(sample_repo, 1, {})

    def test_missing_language_shows_na(self, sample_repo):
        sample_repo["language"] = None
        assert "N/A" in m.format_repo(sample_repo, 1, {})

    def test_description_truncated_to_80_chars(self, sample_repo):
        sample_repo["description"] = "x" * 200
        out = m.format_repo(sample_repo, 1, {})
        assert "x" * 80 in out
        assert "x" * 81 not in out


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
        assert "stars:>10" in mock_get.call_args_list[0].kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_browse_mode_active_giants_uses_stars_gt_1000(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        assert "stars:>1000" in mock_get.call_args_list[1].kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_new_relevant_uses_stars_gt_50(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        q = mock_get.call_args_list[0].kwargs["params"]["q"]
        assert "stars:>50" in q
        assert "stars:>10" not in q

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_active_relevant_uses_stars_gt_500(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        q = mock_get.call_args_list[1].kwargs["params"]["q"]
        assert "stars:>500" in q
        assert "stars:>1000" not in q

    @patch("github_repo_of_the_day.requests.get")
    def test_search_mode_preserves_time_dimension(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="MCP", since_days=7)
        for c in mock_get.call_args_list:
            q = c.kwargs["params"]["q"]
            assert "created:>=" in q or "pushed:>=" in q

    @patch("github_repo_of_the_day.requests.get")
    def test_deduplication_across_categories(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/shared")])
        result = m.search_trending_repos()
        ids = [r["id"] for repos in result.values() for r in repos]
        assert ids.count(1) == 1

    @patch("github_repo_of_the_day.requests.get")
    def test_language_filter_appended_to_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(language="rust")
        for c in mock_get.call_args_list:
            assert "language:rust" in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_single_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM")
        for c in mock_get.call_args_list:
            assert '"LLM"' in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_multi_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        for c in mock_get.call_args_list:
            assert '"LLM agent"' in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_includes_in_scope(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="MCP", search_in="name,description")
        for c in mock_get.call_args_list:
            assert "in:name,description" in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_no_keyword_produces_no_in_qualifier(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        for c in mock_get.call_args_list:
            assert " in:" not in c.kwargs["params"]["q"]

    def test_invalid_search_in_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid search_in"):
            m.search_trending_repos(keyword="test", search_in="topics")

    def test_invalid_search_in_error_lists_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            m.search_trending_repos(keyword="test", search_in="xyz,topics")
        msg = str(exc_info.value)
        assert "name" in msg and "description" in msg and "readme" in msg

    def test_valid_search_in_tokens_do_not_raise(self):
        valid_combos = [
            "name", "description", "readme",
            "name,description", "name,readme", "description,readme",
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


# ──────────────────────────────────────────────
# build_keyword_qualifier  (Priority B)
# ──────────────────────────────────────────────

class TestBuildKeywordQualifier:
    def test_single_keyword_is_quoted(self):
        assert '"LLM"' in m.build_keyword_qualifier(["LLM"])

    def test_single_multi_word_keyword_is_quoted_as_phrase(self):
        result = m.build_keyword_qualifier(["LLM agent"])
        assert '"LLM agent"' in result
        assert '"LLM" "agent"' not in result

    def test_single_keyword_appends_in_scope(self):
        assert "in:name,description" in m.build_keyword_qualifier(["LLM"], search_in="name,description")

    def test_single_keyword_default_scope_is_name_and_description(self):
        assert "in:name,description" in m.build_keyword_qualifier(["MCP"])

    def test_two_keywords_joined_with_and_by_default(self):
        assert '"LLM" AND "agent"' in m.build_keyword_qualifier(["LLM", "agent"])

    def test_three_keywords_joined_with_and(self):
        assert '"LLM" AND "agent" AND "python"' in m.build_keyword_qualifier(["LLM", "agent", "python"])

    def test_two_keywords_joined_with_or(self):
        assert '"LLM" OR "GPT"' in m.build_keyword_qualifier(["LLM", "GPT"], keyword_op="OR")

    def test_three_keywords_joined_with_or(self):
        assert '"LLM" OR "GPT" OR "Claude"' in m.build_keyword_qualifier(["LLM", "GPT", "Claude"], keyword_op="OR")

    def test_or_connector_does_not_produce_and(self):
        assert '"LLM" AND "GPT"' not in m.build_keyword_qualifier(["LLM", "GPT"], keyword_op="OR")

    def test_keyword_op_lowercase_and_accepted(self):
        assert '"LLM" AND "agent"' in m.build_keyword_qualifier(["LLM", "agent"], keyword_op="and")

    def test_keyword_op_lowercase_or_accepted(self):
        assert '"LLM" OR "GPT"' in m.build_keyword_qualifier(["LLM", "GPT"], keyword_op="or")

    def test_keyword_op_mixed_case_accepted(self):
        assert '"LLM" AND "agent"' in m.build_keyword_qualifier(["LLM", "agent"], keyword_op="And")

    def test_keyword_op_with_whitespace_accepted(self):
        assert '"LLM" AND "agent"' in m.build_keyword_qualifier(["LLM", "agent"], keyword_op="  AND  ")

    def test_invalid_keyword_op_raises_value_error(self):
        with pytest.raises(ValueError, match="keyword_op"):
            m.build_keyword_qualifier(["LLM"], keyword_op="XOR")

    def test_invalid_keyword_op_error_mentions_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            m.build_keyword_qualifier(["LLM"], keyword_op="NAND")
        msg = str(exc_info.value)
        assert "AND" in msg and "OR" in msg

    def test_single_not_term_excluded(self):
        assert 'NOT "benchmark"' in m.build_keyword_qualifier(["LLM"], keyword_not=["benchmark"])

    def test_multiple_not_terms_all_excluded(self):
        result = m.build_keyword_qualifier(["LLM"], keyword_not=["benchmark", "survey"])
        assert 'NOT "benchmark"' in result
        assert 'NOT "survey"' in result

    def test_not_terms_appear_after_positive_terms(self):
        result = m.build_keyword_qualifier(["LLM"], keyword_not=["benchmark"])
        assert result.index('"LLM"') < result.index('NOT "benchmark"')

    def test_not_term_multi_word_is_quoted_as_phrase(self):
        assert 'NOT "large benchmark"' in m.build_keyword_qualifier(["LLM"], keyword_not=["large benchmark"])

    def test_empty_keyword_not_list_produces_no_not_clause(self):
        assert "NOT" not in m.build_keyword_qualifier(["LLM"], keyword_not=[])

    def test_and_plus_not(self):
        result = m.build_keyword_qualifier(["LLM", "agent"], keyword_op="AND", keyword_not=["benchmark"])
        assert '"LLM" AND "agent"' in result
        assert 'NOT "benchmark"' in result

    def test_or_plus_not(self):
        result = m.build_keyword_qualifier(["LLM", "GPT"], keyword_op="OR", keyword_not=["survey"])
        assert '"LLM" OR "GPT"' in result
        assert 'NOT "survey"' in result

    def test_empty_keywords_returns_empty_string(self):
        assert m.build_keyword_qualifier([]) == ""

    def test_empty_keywords_with_not_terms_returns_empty_string(self):
        assert m.build_keyword_qualifier([], keyword_not=["benchmark"]) == ""

    def test_keyword_with_leading_trailing_spaces_stripped(self):
        result = m.build_keyword_qualifier(["  LLM  "])
        assert '"LLM"' in result
        assert '"  LLM  "' not in result

    def test_in_scope_appears_once_regardless_of_keyword_count(self):
        result = m.build_keyword_qualifier(["LLM", "GPT", "Claude"], keyword_op="OR", search_in="name,description")
        assert result.count("in:name,description") == 1

    def test_invalid_search_in_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid search_in"):
            m.build_keyword_qualifier(["LLM"], search_in="topics")


# ──────────────────────────────────────────────
# search_trending_repos — multi-keyword integration
# ──────────────────────────────────────────────

class TestSearchTrendingReposMultiKeyword:
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
    def test_two_keywords_and_both_appear_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "agent"], keyword_op="AND")
        for c in mock_get.call_args_list:
            assert '"LLM" AND "agent"' in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_two_keywords_or_both_appear_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "GPT"], keyword_op="OR")
        for c in mock_get.call_args_list:
            assert '"LLM" OR "GPT"' in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_not_produces_not_clause_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM"], keyword_not=["benchmark"])
        for c in mock_get.call_args_list:
            assert 'NOT "benchmark"' in c.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_triggers_search_mode_categories(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keywords=["LLM", "agent"])
        assert set(result.keys()) == {"New & Relevant", "Active & Relevant"}

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_preserves_time_filter(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "agent"], since_days=7)
        for c in mock_get.call_args_list:
            q = c.kwargs["params"]["q"]
            assert "created:>=" in q or "pushed:>=" in q

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_in_scope_appears_once(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "GPT", "Claude"], keyword_op="OR", search_in="name,description")
        for c in mock_get.call_args_list:
            assert c.kwargs["params"]["q"].count("in:name,description") == 1

    @patch("github_repo_of_the_day.requests.get")
    def test_keywords_and_keyword_both_raise_value_error(self, mock_get):
        mock_get.return_value = _mock_response([])
        with pytest.raises(ValueError, match="keyword.*keywords"):
            m.search_trending_repos(keyword="LLM", keywords=["LLM", "agent"])

    @patch("github_repo_of_the_day.requests.get")
    def test_empty_keywords_list_falls_back_to_browse_mode(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keywords=[])
        assert set(result.keys()) == {"New Today", "Active Giants"}

    @patch("github_repo_of_the_day.requests.get")
    def test_single_item_keywords_list_equivalent_to_keyword(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM"])
        for c in mock_get.call_args_list:
            q = c.kwargs["params"]["q"]
            assert '"LLM"' in q and "in:name,description" in q


# ──────────────────────────────────────────────
# parse_boolean_query  (Priority C — full Boolean parser)
#
# Contract:
#   @dataclass
#   class Term:
#       value:   str
#       negated: bool = False
#
#   @dataclass
#   class BoolNode:
#       op:       str          # "AND" | "OR"
#       children: list         # list[Term | BoolNode]
#
#   parse_boolean_query(expr: str) -> BoolNode | Term
#
# Rules enforced by this test class:
#   - Single bare term            → Term(value, negated=False)
#   - "NOT term"                  → Term(value, negated=True)
#   - "A AND B"                   → BoolNode("AND", [Term(A), Term(B)])
#   - "A OR B"                    → BoolNode("OR",  [Term(A), Term(B)])
#   - "(A OR B) AND C"            → BoolNode("AND", [BoolNode("OR", [...]), Term(C)])
#   - "A AND NOT B"               → BoolNode("AND", [Term(A), Term(B, negated=True)])
#   - operators are case-insensitive and whitespace-normalised
#   - empty string                → ValueError
#   - unbalanced parentheses      → ValueError
#   - two consecutive terms       → ValueError (missing operator)
#   - dangling operator           → ValueError (op with no RHS)
# ──────────────────────────────────────────────

class TestParseBooleanQuery:
    """Unit tests for parse_boolean_query()."""

    # ── single term ──

    def test_single_term_returns_term_node(self):
        result = m.parse_boolean_query("LLM")
        assert isinstance(result, m.Term)

    def test_single_term_value_is_preserved(self):
        result = m.parse_boolean_query("LLM")
        assert result.value == "LLM"

    def test_single_term_is_not_negated(self):
        result = m.parse_boolean_query("LLM")
        assert result.negated is False

    def test_single_term_with_surrounding_whitespace(self):
        result = m.parse_boolean_query("  LLM  ")
        assert isinstance(result, m.Term)
        assert result.value == "LLM"

    def test_single_quoted_phrase_returns_term(self):
        """A quoted multi-word phrase is a single Term, not two."""
        result = m.parse_boolean_query('"LLM agent"')
        assert isinstance(result, m.Term)
        assert result.value == "LLM agent"

    # ── NOT (negation) ──

    def test_not_term_returns_negated_term(self):
        result = m.parse_boolean_query("NOT benchmark")
        assert isinstance(result, m.Term)
        assert result.negated is True

    def test_not_term_value_is_correct(self):
        result = m.parse_boolean_query("NOT benchmark")
        assert result.value == "benchmark"

    def test_not_is_case_insensitive(self):
        result = m.parse_boolean_query("not benchmark")
        assert isinstance(result, m.Term)
        assert result.negated is True

    def test_not_quoted_phrase(self):
        result = m.parse_boolean_query('NOT "large benchmark"')
        assert isinstance(result, m.Term)
        assert result.value == "large benchmark"
        assert result.negated is True

    # ── AND ──

    def test_a_and_b_returns_bool_node(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert isinstance(result, m.BoolNode)

    def test_a_and_b_op_is_and(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert result.op == "AND"

    def test_a_and_b_has_two_children(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert len(result.children) == 2

    def test_a_and_b_children_are_terms(self):
        result = m.parse_boolean_query("LLM AND agent")
        assert all(isinstance(c, m.Term) for c in result.children)

    def test_a_and_b_child_values(self):
        result = m.parse_boolean_query("LLM AND agent")
        values = [c.value for c in result.children]
        assert values == ["LLM", "agent"]

    def test_three_terms_and_has_three_children(self):
        result = m.parse_boolean_query("LLM AND agent AND python")
        assert isinstance(result, m.BoolNode)
        assert result.op == "AND"
        assert len(result.children) == 3

    # ── OR ──

    def test_a_or_b_op_is_or(self):
        result = m.parse_boolean_query("LLM OR GPT")
        assert isinstance(result, m.BoolNode)
        assert result.op == "OR"

    def test_a_or_b_child_values(self):
        result = m.parse_boolean_query("LLM OR GPT")
        assert [c.value for c in result.children] == ["LLM", "GPT"]

    # ── operator case-insensitivity ──

    def test_and_lowercase_accepted(self):
        result = m.parse_boolean_query("LLM and agent")
        assert isinstance(result, m.BoolNode)
        assert result.op == "AND"

    def test_or_lowercase_accepted(self):
        result = m.parse_boolean_query("LLM or GPT")
        assert isinstance(result, m.BoolNode)
        assert result.op == "OR"

    # ── nested groups (parentheses) ──

    def test_grouped_or_and_term_returns_bool_node(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent")
        assert isinstance(result, m.BoolNode)
        assert result.op == "AND"

    def test_grouped_or_is_first_child(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent")
        first = result.children[0]
        assert isinstance(first, m.BoolNode)
        assert first.op == "OR"

    def test_grouped_or_children_correct(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent")
        inner = result.children[0]
        assert [c.value for c in inner.children] == ["LLM", "GPT"]

    def test_second_child_of_outer_and_is_term(self):
        result = m.parse_boolean_query("(LLM OR GPT) AND agent")
        assert isinstance(result.children[1], m.Term)
        assert result.children[1].value == "agent"

    def test_full_expression_three_clauses(self):
        """(LLM OR GPT) AND agent AND NOT benchmark"""
        result = m.parse_boolean_query("(LLM OR GPT) AND agent AND NOT benchmark")
        assert isinstance(result, m.BoolNode)
        assert result.op == "AND"
        assert len(result.children) == 3
        # first child: inner OR group
        assert isinstance(result.children[0], m.BoolNode)
        assert result.children[0].op == "OR"
        # second child: plain term
        assert isinstance(result.children[1], m.Term)
        assert result.children[1].value == "agent"
        assert result.children[1].negated is False
        # third child: negated term
        assert isinstance(result.children[2], m.Term)
        assert result.children[2].value == "benchmark"
        assert result.children[2].negated is True

    def test_not_inside_group(self):
        """(LLM AND NOT survey) OR GPT"""
        result = m.parse_boolean_query("(LLM AND NOT survey) OR GPT")
        assert result.op == "OR"
        inner = result.children[0]
        assert inner.op == "AND"
        assert inner.children[1].negated is True
        assert inner.children[1].value == "survey"

    # ── error handling ──

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            m.parse_boolean_query("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            m.parse_boolean_query("   ")

    def test_unclosed_paren_raises_value_error(self):
        with pytest.raises(ValueError, match="[Pp]arenthes"):
            m.parse_boolean_query("(LLM OR GPT AND agent")

    def test_unopened_paren_raises_value_error(self):
        with pytest.raises(ValueError, match="[Pp]arenthes"):
            m.parse_boolean_query("LLM OR GPT) AND agent")

    def test_dangling_operator_at_end_raises_value_error(self):
        """'LLM AND' has no RHS — must raise."""
        with pytest.raises(ValueError):
            m.parse_boolean_query("LLM AND")

    def test_dangling_not_at_end_raises_value_error(self):
        """'LLM AND NOT' has no operand for NOT — must raise."""
        with pytest.raises(ValueError):
            m.parse_boolean_query("LLM AND NOT")

    def test_consecutive_terms_without_operator_raises_value_error(self):
        """'LLM agent' is ambiguous — missing operator must raise."""
        with pytest.raises(ValueError, match="[Oo]perator"):
            m.parse_boolean_query("LLM agent")


# ──────────────────────────────────────────────
# build_keyword_qualifier — AST overload
#
# build_keyword_qualifier() must accept a BoolNode or Term as its first
# argument in addition to list[str], and serialise the AST to a GitHub
# Search query fragment.
#
# Serialisation rules:
#   Term(value, negated=False) → '"value"'
#   Term(value, negated=True)  → 'NOT "value"'
#   BoolNode("AND", [A, B])    → '<A> AND <B> in:<search_in>'
#   BoolNode("OR",  [A, B])    → '<A> OR <B> in:<search_in>'
#   Nested BoolNode            → '(<inner>) AND/OR … in:<search_in>'
#   in: qualifier appears exactly once (after the outermost node)
# ──────────────────────────────────────────────

class TestBuildKeywordQualifierFromAST:
    """build_keyword_qualifier() accepting BoolNode / Term input."""

    def test_term_node_produces_quoted_value(self):
        node = m.Term("LLM")
        result = m.build_keyword_qualifier(node)
        assert '"LLM"' in result

    def test_negated_term_node_produces_not_clause(self):
        node = m.Term("benchmark", negated=True)
        result = m.build_keyword_qualifier(node)
        assert 'NOT "benchmark"' in result

    def test_term_node_appends_in_scope(self):
        node = m.Term("LLM")
        result = m.build_keyword_qualifier(node, search_in="name,description")
        assert "in:name,description" in result

    def test_bool_node_and_serialised_correctly(self):
        node = m.BoolNode("AND", [m.Term("LLM"), m.Term("agent")])
        result = m.build_keyword_qualifier(node)
        assert '"LLM" AND "agent"' in result

    def test_bool_node_or_serialised_correctly(self):
        node = m.BoolNode("OR", [m.Term("LLM"), m.Term("GPT")])
        result = m.build_keyword_qualifier(node)
        assert '"LLM" OR "GPT"' in result

    def test_nested_bool_node_inner_group_is_parenthesised(self):
        """Inner BoolNode must be wrapped in parens to preserve precedence."""
        inner = m.BoolNode("OR", [m.Term("LLM"), m.Term("GPT")])
        outer = m.BoolNode("AND", [inner, m.Term("agent")])
        result = m.build_keyword_qualifier(outer)
        assert '("LLM" OR "GPT")' in result
        assert "AND" in result
        assert '"agent"' in result

    def test_negated_term_inside_bool_node(self):
        node = m.BoolNode("AND", [m.Term("LLM"), m.Term("benchmark", negated=True)])
        result = m.build_keyword_qualifier(node)
        assert '"LLM"' in result
        assert 'NOT "benchmark"' in result

    def test_in_scope_appears_exactly_once_for_nested_ast(self):
        """in: must not leak into inner group serialisation."""
        inner = m.BoolNode("OR", [m.Term("LLM"), m.Term("GPT")])
        outer = m.BoolNode("AND", [inner, m.Term("agent")])
        result = m.build_keyword_qualifier(outer, search_in="name,description")
        assert result.count("in:name,description") == 1

    def test_full_expression_round_trip(self):
        """parse → build round-trip for '(LLM OR GPT) AND agent AND NOT benchmark'."""
        ast = m.parse_boolean_query("(LLM OR GPT) AND agent AND NOT benchmark")
        result = m.build_keyword_qualifier(ast, search_in="name,description")
        assert '("LLM" OR "GPT")' in result
        assert 'AND "agent"' in result
        assert 'NOT "benchmark"' in result
        assert result.count("in:name,description") == 1

    def test_invalid_search_in_raises_for_ast_input(self):
        node = m.Term("LLM")
        with pytest.raises(ValueError, match="Invalid search_in"):
            m.build_keyword_qualifier(node, search_in="topics")
