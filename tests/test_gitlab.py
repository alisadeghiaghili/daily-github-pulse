"""
tests/test_gitlab.py — Tests for the GitLab forge implementation.

All API calls are mocked — no network access required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forges.gitlab import GitLabClient
from forges.base import ForgeRepo, ForgeUser


@pytest.fixture()
def client():
    return GitLabClient(token="glpat_test_token")


@pytest.fixture()
def sample_project():
    return {
        "id": 12345,
        "path_with_namespace": "owner/repo",
        "star_count": 5000,
        "forks_count": 200,
        "description": "A test project",
        "created_at": "2025-01-01T00:00:00Z",
        "last_activity_at": "2026-06-01T00:00:00Z",
        "web_url": "https://gitlab.com/owner/repo",
    }


class TestGitLabClient:
    def test_init_with_token(self):
        client = GitLabClient(token="glpat_test")
        assert client.token == "glpat_test"

    def test_init_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "glpat_env")
        client = GitLabClient()
        assert client.token == "glpat_env"

    def test_custom_base_url(self):
        client = GitLabClient(token="test", base_url="https://my-gitlab.com/api/v4")
        assert client.base_url == "https://my-gitlab.com/api/v4"

    def test_get_token_env_var(self, client):
        assert client.get_token_env_var() == "GITLAB_TOKEN"

    @patch("forges.gitlab.requests.get")
    def test_search_repos(self, mock_get, client, sample_project):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [sample_project]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)

        assert len(results) > 0
        for repos in results.values():
            for repo in repos:
                assert isinstance(repo, ForgeRepo)
                assert repo.forge == "gitlab"

    @patch("forges.gitlab.requests.get")
    def test_search_repos_empty(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        results = client.search_repos(since_days=1, top_n=5)
        assert results == {}

    @patch("forges.gitlab.requests.get")
    def test_fetch_readme(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# README"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = client.fetch_readme("owner/repo")
        assert result == "# README"

    @patch("forges.gitlab.requests.get")
    def test_search_developers(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "username": "testuser",
                "name": "Test User",
                "organization": None,
                "location": "Earth",
                "bio": "Tester",
                "projects_count": 10,
                "web_url": "https://gitlab.com/testuser",
            }
        ]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        users = client.search_developers(top_n=1)
        assert len(users) == 1
        assert isinstance(users[0], ForgeUser)
        assert users[0].forge == "gitlab"
