"""Shared HTTP session helpers and rate-limit-aware JSON access."""

from __future__ import annotations

from typing import Any

import requests

DEFAULT_TIMEOUT = 15


class RateLimitError(RuntimeError):
    """Raised when an API responds with an exhausted rate limit."""

    def __init__(self, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class HttpError(RuntimeError):
    """Raised for non-rate-limit HTTP failures after response inspection."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def open_session(
    token: str | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
    bearer: bool = True,
) -> requests.Session:
    """
    Create a configured ``requests.Session``.

    Args:
        token: Optional API token. When ``bearer`` is true the token is sent
            as ``Authorization: Bearer <token>``.
        extra_headers: Additional headers merged into the session.
        bearer: Use Bearer scheme (GitHub/OpenAI). Set false for forges that
            use a custom header (callers should pass that via extra_headers).

    Returns:
        An open :class:`requests.Session`.
    """
    session = requests.Session()
    if token and bearer:
        session.headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        session.headers.update(extra_headers)
    session.headers.setdefault("User-Agent", "daily-github-pulse")
    return session


def _is_rate_limited(response: requests.Response) -> bool:
    """Return True when the response looks like an exhausted rate limit."""
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining == "0":
        return True
    body = (response.text or "").lower()
    return "rate limit" in body


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """
    Perform an HTTP request and return parsed JSON.

    Args:
        session: Configured session from :func:`open_session`.
        url: Absolute request URL.
        params: Query string parameters.
        timeout: Request timeout in seconds.
        method: HTTP method.
        json_body: Optional JSON body for POST/PUT.
        headers: Optional per-request headers.

    Returns:
        Parsed JSON payload.

    Raises:
        RateLimitError: On 429 or 403 with exhausted quota.
        HttpError: On other non-success status codes.
        requests.RequestException: On transport failures.
    """
    response = session.request(
        method,
        url,
        params=params,
        json=json_body,
        headers=headers,
        timeout=timeout,
    )
    if _is_rate_limited(response):
        retry_after = response.headers.get("Retry-After")
        raise RateLimitError(
            f"Rate limit exceeded for {url}. "
            "Authenticate with a token or wait before retrying.",
            retry_after=retry_after,
        )
    if not response.ok:
        raise HttpError(
            f"HTTP {response.status_code} for {url}: {response.text[:200]}",
            status_code=response.status_code,
        )
    return response.json()
