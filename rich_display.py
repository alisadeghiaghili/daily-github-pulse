"""Compatibility shim for rich_display → daily_github_pulse.display.rich."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from daily_github_pulse.display.rich import (  # noqa: E402,F401
    RICH_AVAILABLE,
    console,
    format_velocity_markup,
    make_ai_filter_progress,
    print_developer_table,
    print_header,
    print_repo_table,
)

__all__ = [
    "RICH_AVAILABLE",
    "console",
    "format_velocity_markup",
    "make_ai_filter_progress",
    "print_developer_table",
    "print_header",
    "print_repo_table",
]
