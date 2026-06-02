"""
Test suite for daily-github-pulse.

Covers all public functions in github_repo_of_the_day.py.
All GitHub API calls are mocked — no network access required.

Run:
    pytest tests/ -v
    pytest tests/ -v --tb=short
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
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _mock_response(items: list) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"items": items}
    resp.raise_for_status.return_value = None
    return resp


def _mock_user_response(user: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = user
    resp.raise_for_status.return_value = None
    return resp


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture()
def sample_repo() -> dict:
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
    return {
        "owner/repo": {
            "stars": 12400,
            "saved_at": _ts(days_ago=2),
        }
    }


@pytest.fixture()
def tmp_snapshot_file(tmp_path, monkeypatch) -> Path:
    snap_dir = tmp_path / ".daily-github-pulse"
    snap_file = snap_dir / "snapshots.json"
    monkeypatch.setattr(m, "SNAPSHOT_DIR", snap_dir)
    monkeypatch.setattr(m, "SNAPSHOT_FILE", snap_file)
    return snap_file


@pytest.fixture()
def sample_user() -> dict:
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
            json.dumps(sample_snapshots, ensure_ascii=False), encoding="utf-8"
        )
        assert m.load_snapshots() == sample_snapshots


# ──────────────────────────────────────────────
# save_snapshots
# ──────────────────────────────────────────────

class TestSaveSnapshots:
    def _make_repos(self, full_name: str, stars: int) -> dict:
        return {"Category": [{"full_name": full_name, "stargazers_count": stars, "id": 1}]}

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
    def test_none_delta_shows_first_run_message(self):
        assert "first run" in m.format_velocity(None, None)

    def test_none_velocity_shows_first_run_message(self):
        assert "first run" in m.format_velocity(None, None)

    def test_positive_delta_shows_plus_sign(self):
        assert "+142" in m.format_velocity(142, 71.0)

    def test_zero_delta(self):
        assert "⭐" in m.format_velocity(0, 0.0)

    def test_negative_delta_no_plus_sign(self):
        result = m.format_velocity(-3, -1.5)
        assert "-3" in result
        assert "+-3" not in result

    def test_large_number_uses_comma_separator(self):
        assert "10,000" in m.format_velocity(10000, 5000.0)

    def test_velocity_shown_in_output(self):
        assert "100.0" in m.format_velocity(700, 100.0)

    def test_output_contains_per_day(self):
        assert "/day" in m.format_velocity(200, 50.0)


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
# expand_wildcards
# ──────────────────────────────────────────────

class TestExpandWildcards:
    def test_no_wildcard_unchanged(self):
        assert m.expand_wildcards("agent") == "agent"

    def test_single_wildcard_produces_or_expression(self):
        result = m.expand_wildcards("analy?e")
        assert "analyse" in result
        assert "analyze" in result
        assert " OR " in result

    def test_single_wildcard_produces_26_variants(self):
        result = m.expand_wildcards("analy?e")
        variants = result.split(" OR ")
        assert len(variants) == 26

    def test_all_variants_have_correct_length(self):
        result = m.expand_wildcards("te?t")
        for v in result.split(" OR "):
            assert len(v) == 4

    def test_wildcard_at_start(self):
        result = m.expand_wildcards("?ython")
        assert "python" in result

    def test_wildcard_at_end(self):
        result = m.expand_wildcards("color?")
        assert "colors" in result

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            m.expand_wildcards("")

    def test_too_many_expansions_raises(self):
        # t??t = 26^2 = 676 > 20
        with pytest.raises(ValueError, match="max allowed"):
            m.expand_wildcards("t??t")

    def test_custom_max_expansions_respected(self):
        # single ? = 26 variants; set max=30 — should pass
        result = m.expand_wildcards("te?t", max_expansions=30)
        assert len(result.split(" OR ")) == 26

    def test_custom_max_expansions_blocks_overflow(self):
        # single ? = 26 variants; set max=10 — should raise
        with pytest.raises(ValueError, match="max allowed"):
            m.expand_wildcards("te?t", max_expansions=10)

    def test_exactly_at_limit_passes(self):
        # 26 variants, max=26 — boundary: should pass
        result = m.expand_wildcards("te?t", max_expansions=26)
        assert len(result.split(" OR ")) == 26

    def test_one_above_limit_raises(self):
        # 26 variants, max=25 — should raise
        with pytest.raises(ValueError):
            m.expand_wildcards("te?t", max_expansions=25)


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
        assert "  " not in result

    def test_not_with_quoted_phrase(self):
        result = m.parse_boolean_query('agent NOT "code review"')
        assert '-"code review"' in result
        assert "NOT" not in result

    def test_wildcard_expanded_inside_boolean(self):
        """analy?e inside a boolean expression must expand to OR variants."""
        result = m.parse_boolean_query("analy?e AND agent")
        assert "analyse" in result
        assert "analyze" in result
        assert "agent" in result
        assert "AND" not in result

    def test_wildcard_only_expression(self):
        """A bare wildcard term (no boolean operators) is still expanded."""
        result = m.parse_boolean_query("analy?e")
        assert "analyse" in result
        assert "analyze" in result

    def test_wildcard_too_many_raises_inside_boolean(self):
        """Over-limit wildcard inside boolean must propagate ValueError."""
        with pytest.raises(ValueError, match="max allowed"):
            m.parse_boolean_query("t??t AND agent")


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
        for call_args in mock_get.call_args_list:
            q = call_args.kwargs["params"]["q"]
            assert "created:>=" in q or "pushed:>=" in q

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
            assert "language:rust" in call_args.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_single_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM")
        for call_args in mock_get.call_args_list:
            assert '"LLM"' in call_args.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_multi_word_quoted_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM agent")
        for call_args in mock_get.call_args_list:
            assert '"LLM agent"' in call_args.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_keyword_includes_in_scope(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="MCP", search_in="name,description")
        for call_args in mock_get.call_args_list:
            assert "in:name,description" in call_args.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_no_keyword_produces_no_in_qualifier(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword=None)
        for call_args in mock_get.call_args_list:
            assert " in:" not in call_args.kwargs["params"]["q"]

    def test_invalid_search_in_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid search_in"):
            m.search_trending_repos(keyword="test", search_in="topics")

    def test_invalid_search_in_error_lists_valid_options(self):
        with pytest.raises(ValueError) as exc_info:
            m.search_trending_repos(keyword="test", search_in="xyz,topics")
        msg = str(exc_info.value)
        assert "name" in msg and "description" in msg and "readme" in msg

    def test_valid_search_in_tokens_do_not_raise(self):
        valid_combos = ["name", "description", "readme", "name,description",
                        "name,readme", "description,readme", "name,description,readme"]
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
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="LLM OR GPT")
        for call_args in mock_get.call_args_list:
            q = call_args.kwargs["params"]["q"]
            assert "OR" in q
            assert '"LLM OR GPT"' not in q

    @patch("github_repo_of_the_day.requests.get")
    def test_boolean_not_translates_to_minus(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="agent AND NOT benchmark")
        for call_args in mock_get.call_args_list:
            assert "-benchmark" in call_args.kwargs["params"]["q"]

    # ── Wildcard in search_trending_repos ──────────────────────────────────

    @patch("github_repo_of_the_day.requests.get")
    def test_wildcard_keyword_expands_in_query(self, mock_get):
        """A bare wildcard keyword must expand both variants into the query."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keyword="analy?e")
        for call_args in mock_get.call_args_list:
            q = call_args.kwargs["params"]["q"]
            assert "analyse" in q
            assert "analyze" in q

    @patch("github_repo_of_the_day.requests.get")
    def test_wildcard_keyword_uses_search_mode_categories(self, mock_get):
        """A wildcard keyword must trigger search mode, not browse mode."""
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keyword="analy?e")
        assert set(result.keys()) == {"New & Relevant", "Active & Relevant"}

    def test_wildcard_over_limit_raises_from_search(self):
        """Over-limit wildcard must raise before any API call."""
        with pytest.raises(ValueError, match="max allowed"):
            m.search_trending_repos(keyword="t??t")

    # ── Multi-keyword tests ──────────────────────────────────────────────

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_and_both_terms_in_query(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "agent"], keyword_op="AND")
        for call_args in mock_get.call_args_list:
            q = call_args.kwargs["params"]["q"]
            assert '"LLM"' in q
            assert '"agent"' in q

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_or_uses_or_operator(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "GPT"], keyword_op="OR")
        for call_args in mock_get.call_args_list:
            assert "OR" in call_args.kwargs["params"]["q"]

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_returns_relevant_categories(self, mock_get):
        mock_get.return_value = _mock_response([self._repo(1, "owner/alpha")])
        result = m.search_trending_repos(keywords=["LLM", "agent"])
        assert set(result.keys()) == {"New & Relevant", "Active & Relevant"}

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_includes_in_scope(self, mock_get):
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["LLM", "agent"], search_in="name,description")
        for call_args in mock_get.call_args_list:
            assert "in:name,description" in call_args.kwargs["params"]["q"]

    def test_invalid_keyword_op_raises_value_error(self):
        with pytest.raises(ValueError, match="keyword_op"):
            m.search_trending_repos(keywords=["LLM"], keyword_op="XOR")

    @patch("github_repo_of_the_day.requests.get")
    def test_multi_keyword_with_wildcard_expands(self, mock_get):
        """Wildcard in a multi-keyword list must expand in the query."""
        mock_get.return_value = _mock_response([])
        m.search_trending_repos(keywords=["analy?e", "agent"], keyword_op="AND")
        for call_args in mock_get.call_args_list:
            q = call_args.kwargs["params"]["q"]
            assert "analyse" in q
            assert "analyze" in q
