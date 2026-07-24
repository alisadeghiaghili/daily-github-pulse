"""
tests/test_github.py — Tests for the GitHub forge implementation.

All API calls are mocked — no network access required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forges.github import GitHubClient, _get_headers
from forges.base import ForgeRepo, ForgeUser


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture()
def client():
    """A GitHubClient with a test token."""
    return GitHubClient(token="ghp_test_token")


@pytest.fixture()
def sample_repo_data():
    """Raw GitHub API repo response."""
    return {
        "id": 12345,
        "full_name": "owner/repo",
        "stargazers_count": 5000,
        "forks_count": 200,
        "language": "Python",
        "description": "A test repository",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "html_url": "https://github.com/owner/repo",
    }


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

class TestGetHeaders:
    def test_no_token_omits_authorization(self):
        headers = _get_headers(None)
        assert "Authorization" not in headers

    def test_with_token_includes_bearer(self):
        headers = _get_headers("ghp_test")
        assert headers["Authorization"] == "Bearer ghp_test"

    def test_accept_header_always_present(self):
        headers = _get_headers(None)
        assert "Accept" in headers


class TestGitHubClient:
    def test_init_with_token(self):
        client = GitHubClient(token="ghp_test")
        assert client.token == "ghp_test"

    def test_init_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_env_token")
        client = GitHubClient()
        assert client.token == "ghp_env_token"

    def test_get_token_env_var(self, client):
        assert client.get_token_env_var() == "GITHUB_TOKEN"

    @patch("forges.github.requests.get")
    def test_search_repos_browse_mode(self, mock_get, client, sample_repo_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [sample_repo_data]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)

        assert "New Today" in results or "Active Giants" in results
        assert mock_get.called

    @patch("forges.github.requests.get")
    def test_search_repos_returns_forge_repos(self, mock_get, client, sample_repo_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [sample_repo_data]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)

        for repos in results.values():
            for repo in repos:
                assert isinstance(repo, ForgeRepo)
                assert repo.forge == "github"

    @patch("forges.github.requests.get")
    def test_search_repos_with_language(self, mock_get, client, sample_repo_data):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [sample_repo_data]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        client.search_repos(language="python", since_days=1, top_n=5)

        # Check that language was added to query
        call_args = mock_get.call_args
        assert "language:python" in call_args[1]["params"]["q"]

    @patch("forges.github.requests.get")
    def test_fetch_readme_success(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# README\nThis is a test."
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = client.fetch_readme("owner/repo")
        assert result == "# README\nThis is a test."

    @patch("forges.github.requests.get")
    def test_fetch_readme_404_returns_empty(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = client.fetch_readme("owner/nonexistent")
        assert result == ""

    @patch("forges.github.requests.get")
    def test_search_developers(self, mock_get, client):
        mock_search_resp = MagicMock()
        mock_search_resp.json.return_value = {
            "items": [{"login": "testuser"}]
        }
        mock_search_resp.raise_for_status.return_value = None

        mock_detail_resp = MagicMock()
        mock_detail_resp.json.return_value = {
            "login": "testuser",
            "name": "Test User",
            "company": None,
            "location": "Earth",
            "bio": "Tester",
            "public_repos": 10,
            "followers": 100,
            "following": 50,
            "html_url": "https://github.com/testuser",
        }
        mock_detail_resp.raise_for_status.return_value = None

        mock_get.side_effect = [mock_search_resp, mock_detail_resp]

        users = client.search_developers(top_n=1)
        assert len(users) == 1
        assert isinstance(users[0], ForgeUser)
        assert users[0].login == "testuser"
        assert users[0].forge == "github"
