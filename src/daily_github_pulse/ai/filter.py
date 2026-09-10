"""LLM-based relevance filtering for search results."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import requests

from daily_github_pulse.core.boolean import (  # noqa: F401  re-export surface
    BoolNode,
    Term,
)

RELEVANCE_SYSTEM_PROMPT = (
    "You are a precise relevance classifier for GitHub repositories. "
    "Given a user's intent and a repository's description plus README snippet, "
    "decide if the repository is relevant to the user's intent. "
    "Reply with exactly one line: start with YES or NO, "
    "then a colon and a brief reason (max 15 words). "
    "Example: YES: implements the exact pattern the user described."
)


@dataclass
class AIFilterConfig:
    """Configuration for the LLM-based relevance filter."""

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    max_tokens: int = 64
    timeout: int = 30


def load_ai_filter_config() -> AIFilterConfig | None:
    """
    Build an ``AIFilterConfig`` from environment variables.

    Returns:
        Config when credentials exist, else ``None``.
    """
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5").strip()
        if not api_key:
            return None
        return AIFilterConfig(
            provider="anthropic",
            base_url="",
            model=model,
            api_key=api_key,
        )

    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini").strip()
    if not api_key:
        return None
    return AIFilterConfig(
        provider="openai",
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


def repo_identity(repo) -> tuple[str, str]:
    """
    Extract ``(full_name, description)`` from a repo payload.

    Args:
        repo: Mapping with ``full_name`` / ``description``, or ``ForgeRepo``.

    Returns:
        ``(full_name, description)``; description is ``""`` when missing.

    Raises:
        ValueError: If the object exposes neither shape.
    """
    from daily_github_pulse.forges.base import ForgeRepo

    if isinstance(repo, ForgeRepo):
        return repo.full_name, (repo.description or "")
    if isinstance(repo, dict):
        return repo["full_name"], (repo.get("description") or "")
    raise ValueError(f"Unsupported repo type for identity: {type(repo)!r}")


def fetch_readme_snippet(
    full_name: str,
    max_chars: int = 800,
    token: str | None = None,
) -> str:
    """
    Fetch the first ``max_chars`` characters of a repo's README.

    Args:
        full_name: Repository full name, e.g. ``"owner/repo"``.
        max_chars: Maximum characters to return.
        token: Optional GitHub token; falls back to ``GITHUB_TOKEN``.

    Returns:
        README snippet, or ``""`` if unavailable.
    """
    import os as _os

    headers = {"Accept": "application/vnd.github.raw+json"}
    effective = token or _os.getenv("GITHUB_TOKEN")
    if effective:
        headers["Authorization"] = f"Bearer {effective}"

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        return resp.text[:max_chars]
    except (requests.RequestException, UnicodeDecodeError):
        return ""


def call_openai_compatible(
    config: AIFilterConfig,
    system_prompt: str,
    user_message: str,
) -> str:
    """Call any OpenAI-compatible chat completions endpoint."""
    resp = requests.post(
        f"{config.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": config.max_tokens,
            "temperature": 0,
        },
        timeout=config.timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Unexpected LLM response shape: {data}") from exc


def call_anthropic(
    config: AIFilterConfig,
    system_prompt: str,
    user_message: str,
) -> str:
    """Call the Anthropic Messages API."""
    try:
        import anthropic as _anthropic  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for AI_PROVIDER=anthropic. "
            "Install it with: pip install anthropic"
        ) from exc

    client = _anthropic.Anthropic(
        api_key=config.api_key,
        timeout=config.timeout,
    )
    msg = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return msg.content[0].text.strip()


def is_repo_relevant(
    repo,
    query: str,
    config: AIFilterConfig,
) -> tuple[bool, str]:
    """
    Ask the LLM whether a repository is relevant to ``query``.

    Args:
        repo:   Repository dict, or ``ForgeRepo``.
        query:  Natural-language description of user intent.
        config: Backend credentials and model.

    Returns:
        ``(relevant, reason)``.
    """
    full_name, description_raw = repo_identity(repo)
    description = description_raw.strip()
    readme = fetch_readme_snippet(full_name)

    user_message = (
        f"User intent: {query}\n\n"
        f"Repository: {full_name}\n"
        f"Description: {description or 'N/A'}\n"
        f"README snippet:\n{readme or 'N/A'}"
    )

    try:
        if config.provider == "anthropic":
            raw = call_anthropic(config, RELEVANCE_SYSTEM_PROMPT, user_message)
        else:
            raw = call_openai_compatible(config, RELEVANCE_SYSTEM_PROMPT, user_message)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"LLM call failed for {full_name}: {exc}") from exc

    upper = raw.upper()
    relevant = upper.startswith("YES")
    reason = raw.split(":", 1)[-1].strip() if ":" in raw else raw
    return relevant, reason


def apply_ai_filter(
    repos_by_category: dict,
    query: str,
    config: AIFilterConfig,
    fallback: str = "fail",
    verbose: bool = True,
) -> dict:
    """
    Filter categories to only LLM-relevant repositories.

    Args:
        repos_by_category: Search output mapping category → repos.
        query:             Natural-language relevance query.
        config:            LLM backend config.
        fallback:          ``"fail"`` or ``"passthrough"``.
        verbose:           Print per-repo progress to stderr.

    Returns:
        New dict with the same structure, containing only relevant repos.

    Raises:
        RuntimeError: LLM failure when ``fallback`` is ``"fail"``.
        ValueError:   Invalid ``fallback``.
    """
    if fallback not in ("fail", "passthrough"):
        raise ValueError(
            f"Invalid fallback '{fallback}'. Valid options: 'fail', 'passthrough'."
        )

    filtered: dict = {}

    for category, repos in repos_by_category.items():
        kept: list = []
        for repo in repos:
            try:
                relevant, reason = is_repo_relevant(repo, query, config)
            except RuntimeError as exc:
                if fallback == "passthrough":
                    print(
                        "  ⚠  LLM unavailable — showing all results unfiltered.\n"
                        f"     ({exc})",
                        file=sys.stderr,
                    )
                    return repos_by_category
                raise

            if verbose:
                mark = "✓" if relevant else "✗"
                full_name, _ = repo_identity(repo)
                print(f"  {mark} {full_name}  — {reason}", file=sys.stderr)
            if relevant:
                kept.append(repo)

        filtered[category] = kept

    return filtered
