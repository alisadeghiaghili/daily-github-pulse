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
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the project root importable regardless of working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import github_repo_of_the_day as m


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
    """Snapshot data matching ``sample_repo`` with a lower star count."""
    return {
        "owner/repo": {
            "stars": 12400,
            "saved_at": "2026-05-31T10:00:00",
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

    def test_merges_with_existing_data(self, tmp_snapshot_file, sample_snapshots):
        # Write a pre-existing snapshot for a different repo
        existing = {"other/repo": {"stars": 999, "saved_at": "2026-01-01T00:00:00"}}
        tmp_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_snapshot_file.write_text(json.dumps(existing), encoding="utf-8")

        new_repo = {
            "full_name": "owner/new",
            "stargazers_count": 50,
        }
        m.save_snapshots({"New Today": [new_repo]})
        data = json.loads(tmp_snapshot_file.read_text())

        # Both old and new entries should be present
        assert "other/repo" in data
        assert "owner/new" in data

    def test_overwrites_existing_entry_for_same_repo(self, tmp_snapshot_file, sample_repo):
        # Save once
        m.save_snapshots({"New Today": [sample_repo]})
        # Update star count and save again
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
        # current: 12542, previous: 12400
        assert m.star_delta(sample_repo, sample_snapshots) == 142

    def test_zero_delta(self, sample_repo, sample_snapshots):
        repo = {**sample_repo, "stargazers_count": 12400}
        assert m.star_delta(repo, sample_snapshots) == 0

    def test_negative_delta(self, sample_repo, sample_snapshots):
        repo = {**sample_repo, "stargazers_count": 12397}
        assert m.star_delta(repo, sample_snapshots) == -3


# ──────────────────────────────────────────────
# format_velocity
# ──────────────────────────────────────────────

class TestFormatVelocity:
    def test_none_shows_first_run_message(self):
        result = m.format_velocity(None)
        assert "first run" in result
        assert "Δ" in result

    def test_positive_delta_shows_plus_sign(self):
        result = m.format_velocity(142)
        assert "+142" in result
        assert "⭐" in result

    def test_zero_delta(self):
        result = m.format_velocity(0)
        assert "⭐" in result
        assert "+" not in result

    def test_negative_delta_no_plus_sign(self):
        result = m.format_velocity(-3)
        assert "-3" in result
        assert "+" not in result

    def test_large_number_uses_comma_separator(self):
        result = m.format_velocity(10000)
        assert "10,000" in result


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

    def test_with_snapshot_shows_delta(self, sample_repo, sample_snapshots):
        output = m.format_repo(sample_repo, 1, sample_snapshots)
        assert "+142" in output

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
        # The description line should contain exactly 80 x's
        assert "x" * 80 in output
        assert "x" * 81 not in output


# ──────────────────────────────────────────────
# search_trending_repos
# ──────────────────────────────────────────────

def _mock_response(items: list) -> MagicMock:
    """Build a mock requests.Response returning ``items``."""
    resp = MagicMock()
    resp.json.return_value = {"items": items}
    resp.raise_for_status.return_value = None
    return resp


class TestSearchTrendingRepos:
    def test_returns_two_categories(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            result = m.search_trending_repos()
        assert set(result.keys()) == {"New Today", "Active Giants"}

    def test_deduplication_across_categories(self, sample_repo):
        """A repo returned by both queries should appear only in the first."""
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            result = m.search_trending_repos()
        # The same repo (id=1) is returned by both API calls.
        # It must appear in exactly one category.
        all_ids = [
            repo["id"]
            for repos in result.values()
            for repo in repos
        ]
        assert all_ids.count(sample_repo["id"]) == 1

    def test_language_filter_appended_to_query(self, sample_repo):
        with patch("github_repo_of_the_day.requests.get") as mock_get:
            mock_get.return_value = _mock_response([sample_repo])
            m.search_trending_repos(language="python")
        # Both calls should include language:python in the query string
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
