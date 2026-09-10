"""Compatibility shim re-exporting the package forge registry."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from daily_github_pulse.forges import (  # noqa: E402,F401
    DEFAULT_FORGE,
    FORGE_REGISTRY,
    get_forge,
    list_forges,
    register_forge,
)
from daily_github_pulse.forges.base import (  # noqa: E402,F401
    ForgeClient,
    ForgeRepo,
    ForgeUser,
)
from daily_github_pulse.forges.github import GitHubClient  # noqa: E402,F401
from daily_github_pulse.forges.gitlab import GitLabClient  # noqa: E402,F401
from daily_github_pulse.forges.gitea import GiteaClient  # noqa: E402,F401
from daily_github_pulse.forges.bitbucket import BitbucketClient  # noqa: E402,F401

__all__ = [
    "DEFAULT_FORGE",
    "FORGE_REGISTRY",
    "ForgeClient",
    "ForgeRepo",
    "ForgeUser",
    "GitHubClient",
    "GitLabClient",
    "GiteaClient",
    "BitbucketClient",
    "get_forge",
    "list_forges",
    "register_forge",
]
