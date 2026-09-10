"""Compatibility re-export of the GitHub forge client."""

from daily_github_pulse.forges.github import GitHubClient, _get_headers

__all__ = ["GitHubClient", "_get_headers"]
