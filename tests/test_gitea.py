"""
tests/test_gitea.py — Tests for the Gitea/Codeberg forge implementation.

All API calls are mocked — no network access required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forges.gitea import GiteaClient
from forges.base import ForgeRepo, ForgeUser


@pytest.fixture()
def client():
    return GiteaClient(token="gitea_test_token")


@pytest.fixture()
def sample_repo():
    return {
        "id": 12345,
        "full_name": "owner/repo",
        "stargazers_count": 5000,
        "forks_count": 200,
        "language": "Go",
        "description": "A test repo",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-06-01T00:00:00Z",
        "html_url": "https://gitea.com/owner/repo",
    }


class TestGiteaClient:
    def test_init_with_token(self):
        client = GiteaClient(token="gitea_test")
        assert client.token == "gitea_test"

    def test_init_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("GITEA_TOKEN", "gitea_env")
        client = GiteaClient()
        assert client.token == "gitea_env"

    def test_custom_base_url(self):
        client = GiteaClient(token="test", base_url="https://codeberg.org/api/v1")
        assert client.base_url == "https://codeberg.org/api/v1"

    def test_get_token_env_var(self, client):
        assert client.get_token_env_var() == "GITEA_TOKEN"

    @patch("forges.gitea.requests.get")
    def test_search_repos(self, mock_get, client, sample_repo):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [sample_repo]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)

        assert len(results) > 0
        for repos in results.values():
            for repo in repos:
                assert isinstance(repo, ForgeRepo)
                assert repo.forge == "gitea"

    @patch("forges.gitea.requests.get")
    def test_fetch_readme(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# README"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = client.fetch_readme("owner/repo")
        assert result == "# README"

    @patch("forges.gitea.requests.get")
    def test_search_developers(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "login": "testuser",
                    "full_name": "Test User",
                    "organization": None,
                    "location": "Earth",
                    "description": "Tester",
                    "repos_count": 10,
                    "followers_count": 100,
                    "following_count": 50,
                    "html_url": "https://gitea.com/testuser",
                }
            ]
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        users = client.search_developers(top_n=1)
        assert len(users) == 1
        assert isinstance(users[0], ForgeUser)
        assert users[0].forge == "gitea"
