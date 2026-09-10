"""Compatibility re-export of forge data models and the client ABC."""

from daily_github_pulse.forges.base import ForgeClient, ForgeRepo, ForgeUser

__all__ = ["ForgeClient", "ForgeRepo", "ForgeUser"]
