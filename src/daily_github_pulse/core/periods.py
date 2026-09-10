"""Named look-back windows used by the CLI and forge clients."""

from __future__ import annotations

PERIOD_DAYS: dict[str, int] = {
    "day": 1,
    "week": 7,
    "month": 30,
}


def resolve_period(period: str | None, days: int) -> int:
    """
    Resolve the effective look-back window in days.

    ``--period`` takes precedence over ``--days`` when both are supplied.

    Args:
        period: Named period (``"day"``, ``"week"``, ``"month"``) or ``None``.
        days:   Numeric fallback from ``--days``.

    Returns:
        Resolved number of look-back days.

    Raises:
        ValueError: If ``period`` is not a recognised token.

    Examples:
        >>> resolve_period("week", 1)
        7
        >>> resolve_period(None, 3)
        3
    """
    if period is None:
        return days
    key = period.strip().lower()
    if key not in PERIOD_DAYS:
        raise ValueError(
            f"Unknown period '{period}'. Valid options: "
            + ", ".join(PERIOD_DAYS)
        )
    return PERIOD_DAYS[key]
