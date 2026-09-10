#!/usr/bin/env python3
"""
forges/__init__.py — Forge registry and factory.

Provides a decorator-based registration system and a factory function
for creating forge client instances.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ForgeClient

# Registry: forge name → ForgeClient subclass
FORGE_REGISTRY: dict[str, type[ForgeClient]] = {}

# Default forge when none is specified
DEFAULT_FORGE = "github"


def register_forge(name: str):
    """Decorator to register a forge client class.

    Usage::

        @register_forge("github")
        class GitHubClient(ForgeClient):
            ...
    """
    def decorator(cls: type[ForgeClient]) -> type[ForgeClient]:
        FORGE_REGISTRY[name] = cls
        return cls
    return decorator


def get_forge(name: str, token: str | None = None, **kwargs) -> ForgeClient:
    """Factory: return an initialized ForgeClient for the given forge.

    Args:
        name:  Forge identifier (``"github"``, ``"gitlab"``, ``"gitea"``,
               ``"bitbucket"``).
        token: Optional auth token override. If ``None``, the forge's
               default env var is checked.
        **kwargs: Additional forge-specific arguments (e.g. ``base_url``
                  for Gitea instances).

    Returns:
        An initialized :class:`ForgeClient` instance.

    Raises:
        ValueError: If the forge name is not registered.
    """
    # Ensure all forges are imported (triggers registration)
    _ensure_forges_imported()

    if name not in FORGE_REGISTRY:
        available = ", ".join(sorted(FORGE_REGISTRY.keys()))
        raise ValueError(
            f"Unknown forge: {name!r}. Available: {available}"
        )

    cls = FORGE_REGISTRY[name]
    return cls(token=token, **kwargs)


def list_forges() -> list[str]:
    """Return a sorted list of registered forge names."""
    _ensure_forges_imported()
    return sorted(FORGE_REGISTRY.keys())


def _ensure_forges_imported():
    """Import all forge modules to trigger registration decorators."""
    # Lazy import to avoid circular dependencies
    from . import github  # noqa: F401
    from . import gitlab  # noqa: F401
    from . import gitea  # noqa: F401
    from . import bitbucket  # noqa: F401
