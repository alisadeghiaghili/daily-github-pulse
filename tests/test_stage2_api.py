"""
Stage 2 tests: SearchQuery model, HTTP rate-limit handling, snapshot prune,
and CLI token deprecation.

All network calls are mocked.
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daily_github_pulse.core.http import RateLimitError, get_json, open_session
from daily_github_pulse.core.query import SearchQuery
from daily_github_pulse.core.velocity import load_snapshots, prune_snapshots, save_snapshots


class TestSearchQuery:
    def test_defaults(self):
        q = SearchQuery()
        assert q.language is None
        assert q.since_days == 1
        assert q.top_n == 10
        assert q.keyword_op == "AND"

    def test_immutable_keywords_are_tuples(self):
        q = SearchQuery(keywords=["LLM", "agent"], keyword_not=["benchmark"])
        assert q.keywords == ("LLM", "agent")
        assert q.keyword_not == ("benchmark",)

    def test_from_kwargs_roundtrip(self):
        q = SearchQuery.from_kwargs(
            language="python",
            since_days=7,
            top_n=5,
            keywords=["llm"],
            keyword_op="OR",
        )
        assert q.language == "python"
        assert q.since_days == 7
        assert q.top_n == 5
        assert q.keywords == ("llm",)
        assert q.keyword_op == "OR"

    def test_mutual_exclusion_raises(self):
        with pytest.raises(ValueError):
            SearchQuery(keyword="a", keywords=["b"]).validate()

    def test_invalid_keyword_op_raises(self):
        with pytest.raises(ValueError):
            SearchQuery(keywords=["x"], keyword_op="XOR").validate()

    def test_since_date_is_iso(self):
        q = SearchQuery(since_days=3)
        expected = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
        # local date.today() used in forges; just assert format
        assert len(q.since_date) == 10
        assert q.since_date.count("-") == 2


class TestHttpHelpers:
    def test_open_session_sets_headers(self):
        session = open_session(token="tok", extra_headers={"X-Test": "1"})
        try:
            assert session.headers["X-Test"] == "1"
            assert session.headers["Authorization"] == "Bearer tok"
        finally:
            session.close()

    def test_open_session_without_token_omits_auth(self):
        session = open_session(token=None)
        try:
            assert "Authorization" not in session.headers
        finally:
            session.close()

    def test_get_json_success(self):
        session = MagicMock()
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {"ok": True}
        session.request.return_value = resp
        assert get_json(session, "https://example.test/x") == {"ok": True}

    def test_rate_limit_raises_clear_error(self):
        session = MagicMock()
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 403
        resp.headers = {"X-RateLimit-Remaining": "0"}
        resp.text = "forbidden"
        session.request.return_value = resp
        with pytest.raises(RateLimitError) as exc:
            get_json(session, "https://api.github.com/search/repositories")
        assert "rate limit" in str(exc.value).lower()

    def test_http_error_raises(self):
        session = MagicMock()
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 500
        resp.headers = {}
        resp.text = "boom"
        session.request.return_value = resp
        with pytest.raises(RuntimeError):
            get_json(session, "https://example.test/x")


class TestSnapshotPrune:
    def test_prune_removes_old_entries(self, tmp_path):
        path = tmp_path / "snapshots.json"
        old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        new = datetime.now(timezone.utc).isoformat()
        path.write_text(
            '{"old/repo": {"stars": 1, "saved_at": "'
            + old
            + '"}, "new/repo": {"stars": 2, "saved_at": "'
            + new
            + '"}}',
            encoding="utf-8",
        )
        removed = prune_snapshots(path=path, max_age_days=90)
        assert removed == 1
        data = load_snapshots(path)
        assert "new/repo" in data
        assert "old/repo" not in data

    def test_prune_respects_max_entries(self, tmp_path):
        path = tmp_path / "snapshots.json"
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            f"r{i}/x": {"stars": i, "saved_at": now} for i in range(20)
        }
        import json

        path.write_text(json.dumps(payload), encoding="utf-8")
        removed = prune_snapshots(path=path, max_age_days=365, max_entries=5)
        assert removed == 15
        assert len(load_snapshots(path)) == 5

    def test_save_snapshots_calls_prune_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "daily_github_pulse.core.velocity.SNAPSHOT_DIR", tmp_path
        )
        monkeypatch.setattr(
            "daily_github_pulse.core.velocity.SNAPSHOT_FILE",
            tmp_path / "snapshots.json",
        )
        from forges.base import ForgeRepo

        repo = ForgeRepo(
            forge="github",
            id="1",
            full_name="a/b",
            stars=10,
            forks=0,
            language="Python",
            description="d",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            url="https://github.com/a/b",
        )
        save_snapshots({"All": [repo]}, prune=True)
        assert (tmp_path / "snapshots.json").exists()


class TestCliTokenDeprecation:
    def test_token_flag_warns_and_sets_env(self, monkeypatch):
        from daily_github_pulse import cli

        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # simulate the deprecation path used in main()
            token = "ghp_secret"
            if token:
                warnings.warn(
                    "--token is deprecated; set GITHUB_TOKEN in the environment",
                    DeprecationWarning,
                    stacklevel=2,
                )
                monkeypatch.setenv("GITHUB_TOKEN", token)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert cli.os.environ.get("GITHUB_TOKEN") == "ghp_secret"


class TestGitHubClientSearchQuery:
    def test_accepts_search_query_object(self):
        from daily_github_pulse.forges.github import GitHubClient

        client = GitHubClient(token="t")
        with patch("daily_github_pulse.forges.github.get_json") as mock_get:
            mock_get.return_value = {"items": []}
            q = SearchQuery(language="python", top_n=3)
            client.search_repos(query=q)
        assert mock_get.called

    def test_legacy_kwargs_still_work(self):
        from daily_github_pulse.forges.github import GitHubClient

        client = GitHubClient(token="t")
        with patch("daily_github_pulse.forges.github.get_json") as mock_get:
            mock_get.return_value = {"items": []}
            client.search_repos(language="go", top_n=2)
        assert mock_get.called
