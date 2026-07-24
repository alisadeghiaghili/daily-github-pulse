"""
tests/test_bitbucket.py — Tests for the Bitbucket forge implementation.

All API calls are mocked — no network access required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forges.bitbucket import BitbucketClient
from forges.base import ForgeRepo, ForgeUser


@pytest.fixture()
def client():
    return BitbucketClient(username="testuser", app_password="test_pass")


@pytest.fixture()
def sample_repo():
    return {
        "uuid": "{abc-def-123}",
        "full_name": "owner/repo",
        "stargazers_count": 5000,
        "forks_count": 200,
        "language": "Python",
        "description": "A test repo",
        "created_on": "2025-01-01T00:00:00+00:00",
        "updated_on": "2026-06-01T00:00:00+00:00",
        "links": {"html": {"href": "https://bitbucket.org/owner/repo"}},
    }


class TestBitbucketClient:
    def test_init_with_credentials(self):
        client = BitbucketClient(username="user", app_password="pass")
        assert client.username == "user"
        assert client.app_password == "pass"

    def test_init_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_USER", "env_user")
        monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "env_pass")
        client = BitbucketClient()
        assert client.username == "env_user"
        assert client.app_password == "env_pass"

    def test_get_token_env_var(self, client):
        assert client.get_token_env_var() == "BITBUCKET_USER"

    @patch("forges.bitbucket.requests.get")
    def test_search_repos(self, mock_get, client, sample_repo):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"values": [sample_repo]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)

        assert len(results) > 0
        for repos in results.values():
            for repo in repos:
                assert isinstance(repo, ForgeRepo)
                assert repo.forge == "bitbucket"

    @patch("forges.bitbucket.requests.get")
    def test_fetch_readme(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# README"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = client.fetch_readme("owner/repo")
        assert result == "# README"

    def test_search_developers_returns_empty(self, client):
        # Bitbucket doesn't support user search
        users = client.search_developers(top_n=5)
        assert users == []


class TestForgeRegistry:
    def test_list_forges_includes_all(self):
        from forges import list_forges
        forges = list_forges()
        assert "github" in forges
        assert "gitlab" in forges
        assert "gitea" in forges
        assert "bitbucket" in forges

    def test_get_forge_github(self):
        from forges import get_forge
        client = get_forge("github", token="test")
        assert client.__class__.__name__ == "GitHubClient"

    def test_get_forge_gitlab(self):
        from forges import get_forge
        client = get_forge("gitlab", token="test")
        assert client.__class__.__name__ == "GitLabClient"

    def test_get_forge_invalid_raises(self):
        from forges import get_forge
        with pytest.raises(ValueError, match="Unknown forge"):
            get_forge("invalid_forge")
