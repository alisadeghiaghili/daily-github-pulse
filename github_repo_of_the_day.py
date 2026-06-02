#!/usr/bin/env python3
"""
daily-github-pulse  v2.1.0
──────────────────────────
Discover GitHub's top repositories AND developers of the day — with real star velocity.

How velocity works
──────────────────
On each run, star counts are saved to a local snapshot file:
  ~/.daily-github-pulse/snapshots.json

Each snapshot entry stores:
  - stars     : star count at save time
  - saved_at  : UTC ISO timestamp of the save

On the next run two velocity numbers are computed:

  star_delta      — raw difference (current − snapshot), regardless of
                    how much time has passed between runs.

  daily_velocity  — time-normalised rate: star_delta / elapsed_days.
                    This is the number that stays meaningful even if you
                    haven't run the tool for two weeks.
                    Rounded to one decimal place.
                    None when no previous snapshot exists (first run).

Token priority
──────────────
  1. --token CLI flag
  2. GITHUB_TOKEN environment variable / .env file
  3. Unauthenticated  →  60 req/hr limit

Keyword search modes
────────────────────
  --keyword      Single term (legacy).  Searches name+description by default.
  --keywords     Multiple terms joined with AND/OR via --keyword-op.
  --bool-query   Full boolean expression with AND, OR, NOT, parentheses.
                 Parsed into an AST and sent through its own dedicated path —
                 NOT converted to a raw string before being passed down.

Wildcard expansion
──────────────────
  Pass --wildcard to expand ? and * patterns in --keywords before building
  the GitHub query.  Expansion is done client-side against the NLTK words
  corpus (auto-downloaded on first use).  Requires: pip install nltk

  ?  matches exactly one character   analy?e  → analyse OR analyze
  *  matches zero or more characters  optimiz* → optimize OR optimized OR ...

  If NLTK is unavailable the term is passed through unchanged.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Union

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VERSION = "2.1.0"
SNAPSHOT_DIR = Path.home() / ".daily-github-pulse"
SNAPSHOT_FILE = SNAPSHOT_DIR / "snapshots.json"

GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN")

# Named period shortcuts → number of days
PERIOD_DAYS: dict[str, int] = {
    "day":   1,
    "week":  7,
    "month": 30,
}

# Valid tokens for the --search-in / search_in parameter
VALID_SEARCH_IN = {"name", "description", "readme"}

# Valid boolean operators for multi-keyword search
VALID_KEYWORD_OPS = {"AND", "OR"}

# Fields included in JSON / CSV exports (in order)
EXPORT_FIELDS = [
    "rank",
    "category",
    "full_name",
    "stars",
    "star_delta",
    "daily_velocity",
    "forks",
    "language",
    "description",
    "created_at",
    "updated_at",
    "url",
]

# Fields included in developer JSON / CSV exports (in order)
DEV_EXPORT_FIELDS = [
    "rank",
    "login",
    "name",
    "company",
    "location",
    "public_repos",
    "followers",
    "following",
    "url",
]


# ──────────────────────────────────────────────
# Boolean query AST nodes
# ──────────────────────────────────────────────

@dataclass(frozen=True, eq=True)
class Term:
    """
    A single search term, optionally negated.

    Attributes:
        value:   The raw term string (stripped of surrounding quotes).
        negated: True when this term was preceded by NOT.

    Examples:
        >>> Term("LLM")
        Term(value='LLM', negated=False)
        >>> Term("benchmark", negated=True)
        Term(value='benchmark', negated=True)
    """
    value: str
    negated: bool = False


@dataclass(frozen=True, eq=True)
class BoolNode:
    """
    A binary/n-ary boolean expression node.

    Attributes:
        op:       The boolean operator: ``"AND"`` or ``"OR"``.
        children: Two or more child nodes, each a ``Term`` or ``BoolNode``.

    All children in a BoolNode share the same operator.  Mixing AND and OR
    at the same level requires parentheses, which produce nested BoolNodes.

    Examples:
        >>> BoolNode("AND", [Term("LLM"), Term("agent")])
        BoolNode(op='AND', children=[Term(value='LLM', negated=False), ...])
    """
    op: str
    children: list = field(default_factory=list)


# ──────────────────────────────────────────────
# Boolean query parser
# ──────────────────────────────────────────────

def parse_boolean_query(expr: str) -> Union[Term, BoolNode]:
    """
    Parse a Boolean keyword expression into an AST.

    Supported syntax::

        term
        NOT term
        "quoted phrase"
        NOT "quoted phrase"
        A AND B
        A OR B
        A AND B AND C          (flat n-ary AND)
        (A OR B) AND C         (nested groups)
        (A AND NOT B) OR C     (NOT inside a group)

    Operators (AND, OR, NOT) are case-insensitive.
    Leading/trailing whitespace in the expression and around each term
    is stripped.
    Quoted phrases are treated as single terms.

    Args:
        expr: Boolean keyword string.

    Returns:
        A ``Term`` for a single (possibly negated) term, or a ``BoolNode``
        for a compound expression.

    Raises:
        ValueError: If ``expr`` is empty or whitespace-only.
        ValueError: If parentheses are unbalanced.
        ValueError: If two terms appear consecutively without an operator.
        ValueError: If an operator appears with no right-hand operand
                    (dangling AND/OR/NOT).

    Examples:
        >>> parse_boolean_query("LLM")
        Term(value='LLM', negated=False)
        >>> parse_boolean_query("NOT benchmark")
        Term(value='benchmark', negated=True)
        >>> parse_boolean_query("LLM AND agent")
        BoolNode(op='AND', children=[Term(value='LLM', ...), Term(value='agent', ...)])
        >>> parse_boolean_query('(LLM OR GPT) AND agent AND NOT benchmark')
        BoolNode(op='AND', children=[BoolNode(op='OR', ...), Term('agent'), Term('benchmark', negated=True)])
    """
    expr = expr.strip()
    if not expr:
        raise ValueError("parse_boolean_query: expression is empty.")

    tokens = _tokenise(expr)
    ast, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise ValueError(
            f"parse_boolean_query: unexpected token '{tokens[pos]}' "
            f"at position {pos}."
        )
    return ast


# ── internal tokeniser ──────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r'"[^"]*"'          # quoted phrase
    r'|\('              # open paren
    r'|\)'              # close paren
    r'|[^\s()"]+',      # bare word / operator
    re.IGNORECASE,
)


def _tokenise(expr: str) -> list[str]:
    """Split expression into a flat token list."""
    return _TOKEN_RE.findall(expr)


# ── recursive-descent parser ────────────────────────────────────────────────

def _parse_expr(
    tokens: list[str], pos: int, inside_group: bool = False
) -> tuple[Union[Term, BoolNode], int]:
    """
    Parse tokens[pos:] into an AST node.

    Grammar (informal)::

        expr    ::= operand (OP operand)*
        operand ::= NOT? atom
        atom    ::= TERM | '(' expr ')'
        OP      ::= AND | OR

    A group's top-level operator must be homogeneous (all AND or all OR).
    Mixing operators at the same nesting level without parens raises
    ValueError.

    Returns:
        (node, new_pos)
    """
    children: list[Union[Term, BoolNode]] = []
    op: str | None = None
    last_was_operand = False

    while pos < len(tokens):
        tok = tokens[pos]
        upper = tok.upper()

        if tok == ")":
            if not inside_group:
                raise ValueError(
                    "parse_boolean_query: unbalanced parentheses — "
                    f"unexpected ')' at position {pos}."
                )
            break

        if upper in ("AND", "OR"):
            if not children:
                raise ValueError(
                    f"parse_boolean_query: operator '{tok}' at position {pos} "
                    "has no left-hand operand."
                )
            if op is not None and op != upper:
                raise ValueError(
                    f"parse_boolean_query: mixed operators '{op}' and '{upper}' "
                    "at the same level — use parentheses to disambiguate."
                )
            op = upper
            last_was_operand = False
            pos += 1
            continue

        negated = False
        if upper == "NOT":
            pos += 1
            if pos >= len(tokens) or tokens[pos] in ("AND", "OR", "NOT", ")"):
                raise ValueError(
                    f"parse_boolean_query: 'NOT' at position {pos - 1} "
                    "has no operand."
                )
            negated = True
            tok = tokens[pos]

        if last_was_operand:
            raise ValueError(
                f"parse_boolean_query: missing operator before '{tok}' "
                f"at position {pos}. "
                "Did you forget AND or OR?"
            )

        if tok == "(":
            pos += 1
            if pos >= len(tokens):
                raise ValueError(
                    "parse_boolean_query: unbalanced parentheses — "
                    "'(' was never closed."
                )
            child, pos = _parse_expr(tokens, pos, inside_group=True)
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError(
                    "parse_boolean_query: unbalanced parentheses — "
                    "'(' was never closed."
                )
            pos += 1
            children.append(child)
        else:
            value = tok.strip('"')
            children.append(Term(value=value, negated=negated))
            pos += 1

        last_was_operand = True

    if not children:
        raise ValueError(
            "parse_boolean_query: expression is empty or contains only operators."
        )

    if op is not None and len(children) == 1:
        raise ValueError(
            f"parse_boolean_query: dangling operator '{op}' — "
            "no right-hand operand."
        )

    if len(children) == 1:
        return children[0], pos

    if op is None:
        raise ValueError(
            "parse_boolean_query: missing operator between terms."
        )

    return BoolNode(op=op, children=children), pos


# ──────────────────────────────────────────────
# Wildcard expansion
# ──────────────────────────────────────────────

def _load_wordlist() -> set[str] | None:
    """
    Load the NLTK words corpus as a lower-cased set.

    Downloads the corpus automatically on first use if NLTK is available.
    Returns None when NLTK is not installed, so callers can fall back
    gracefully.

    Returns:
        set of lower-cased English words, or None if NLTK is unavailable.
    """
    try:
        import nltk  # type: ignore
        from nltk.corpus import words as nltk_words  # type: ignore
        try:
            word_set = set(w.lower() for w in nltk_words.words())
        except LookupError:
            nltk.download("words", quiet=True)
            word_set = set(w.lower() for w in nltk_words.words())
        return word_set
    except ImportError:
        return None


def expand_wildcards(
    term: str,
    wordlist: set[str] | None = None,
    max_variants: int = 20,
) -> list[str]:
    """
    Expand a wildcard term into matching English words.

    Wildcard syntax::

        ?   matches exactly one character   (single-char slot)
        *   matches zero or more characters  (any-length slot)

    The pattern is anchored to the full word (start and end), so
    ``analy?e`` does NOT match ``analysed`` — only exact-length matches.

    Expansion is done against the NLTK English words corpus.  If NLTK is
    unavailable, the original term is returned as a single-element list
    (no expansion, no crash).

    Args:
        term:         Keyword string that may contain ``?`` and/or ``*``.
        wordlist:     Pre-loaded word set (``set[str]``, lower-cased).
                      Pass ``None`` to trigger lazy loading.
        max_variants: Upper bound on variants returned.  Default: 20.

    Returns:
        List of matching words (lower-cased, deduplicated, sorted).
        Returns ``[term]`` unchanged when no wildcards, NLTK unavailable,
        or no matches found.

    Examples:
        >>> expand_wildcards("analy?e")       # doctest: +SKIP
        ['analyse', 'analyze']
        >>> expand_wildcards("no_wildcard")
        ['no_wildcard']
        >>> expand_wildcards("optimiz*")      # doctest: +SKIP
        ['optimize', 'optimized', 'optimizes', 'optimizing', ...]
    """
    if "?" not in term and "*" not in term:
        return [term]

    if wordlist is None:
        wordlist = _load_wordlist()

    if wordlist is None:
        return [term]

    escaped = re.escape(term)
    pattern = (
        escaped
        .replace(re.escape("?"), r".")
        .replace(re.escape("*"), r".*")
    )
    regex = re.compile(r"^" + pattern + r"$", re.IGNORECASE)

    matches = sorted(
        {w for w in wordlist if regex.match(w)}
    )[:max_variants]

    return matches if matches else [term]


def apply_wildcards_to_keywords(
    keywords: list[str],
    wordlist: set[str] | None = None,
) -> list[str]:
    """
    Expand any wildcard patterns inside a keyword list.

    Each keyword that contains ``?`` or ``*`` is replaced by its expanded
    variants wrapped in parentheses and joined with OR, e.g.::

        ["analy?e", "agent"]
        → ["(analyse OR analyze)", "agent"]

    Keywords without wildcards are returned unchanged.

    Args:
        keywords: List of raw keyword strings (may contain wildcards).
        wordlist: Pre-loaded word set.  When ``None``, corpus is loaded once.

    Returns:
        New list where wildcard terms have been replaced by their expansions.

    Examples:
        >>> apply_wildcards_to_keywords(["analy?e", "agent"])  # doctest: +SKIP
        ['(analyse OR analyze)', 'agent']
        >>> apply_wildcards_to_keywords(["agent"])             # no wildcards
        ['agent']
    """
    if not any("?" in kw or "*" in kw for kw in keywords):
        return keywords

    wl = wordlist if wordlist is not None else _load_wordlist()

    result: list[str] = []
    for kw in keywords:
        if "?" not in kw and "*" not in kw:
            result.append(kw)
        else:
            variants = expand_wildcards(kw, wordlist=wl)
            if len(variants) == 1 and variants[0] == kw:
                result.append(kw)
            else:
                result.append("(" + " OR ".join(variants) + ")")
    return result


# ──────────────────────────────────────────────
# GitHub API helpers
# ──────────────────────────────────────────────
def get_headers() -> dict:
    """Build HTTP headers for the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# ──────────────────────────────────────────────
# Period helpers
# ──────────────────────────────────────────────
def resolve_period(period: str | None, days: int) -> int:
    """
    Resolve the effective look-back window in days.

    ``--period`` takes precedence over ``--days`` when both are supplied.

    Args:
        period: Named period string (``"day"``, ``"week"``, ``"month"``),
                or ``None``.
        days:   Numeric fallback from ``--days`` (default: 1).

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


# ──────────────────────────────────────────────
# Keyword qualifier builder
# ──────────────────────────────────────────────

def _validate_search_in(search_in: str) -> None:
    """Raise ValueError if any token in search_in is invalid."""
    tokens = {t.strip() for t in search_in.split(",") if t.strip()}
    invalid = tokens - VALID_SEARCH_IN
    if invalid:
        raise ValueError(
            f"Invalid search_in value(s): {sorted(invalid)}. "
            f"Valid options: {sorted(VALID_SEARCH_IN)}"
        )


def _serialise_node(node: Union[Term, BoolNode]) -> str:
    """
    Serialise a Term or BoolNode to a GitHub Search query fragment.

    Inner BoolNodes are wrapped in parentheses to preserve operator
    precedence.  The ``in:`` scope qualifier is NOT appended here —
    it is added exactly once by ``build_keyword_qualifier()``.

    Args:
        node: A ``Term`` or ``BoolNode`` from ``parse_boolean_query()``.

    Returns:
        Query fragment string, e.g. ``'("LLM" OR "GPT")'``.
    """
    if isinstance(node, Term):
        quoted = f'"{node.value}"'
        return f'NOT {quoted}' if node.negated else quoted

    parts = []
    for child in node.children:
        if isinstance(child, BoolNode):
            parts.append(f"({_serialise_node(child)})")
        else:
            parts.append(_serialise_node(child))
    return f" {node.op} ".join(parts)


def build_keyword_qualifier(
    keywords: Union[list[str], Term, BoolNode],
    keyword_op: str = "AND",
    keyword_not: list[str] | None = None,
    search_in: str = "name,description",
) -> str:
    """
    Build the keyword fragment of a GitHub Search query string.

    Accepts either a plain ``list[str]`` of terms or a pre-parsed
    ``Term`` / ``BoolNode`` AST node from ``parse_boolean_query()``.

    **List path** — composes terms with a boolean operator, appends
    ``in:`` scope, and optionally appends NOT exclusion terms.

    **AST path** — serialises the AST directly and appends ``in:`` once.
    ``keyword_op`` and ``keyword_not`` are ignored (model exclusions as
    ``Term(negated=True)`` nodes inside the AST).

    Args:
        keywords:    ``list[str]``, a ``Term``, or a ``BoolNode``.
        keyword_op:  Connector for list path: ``"AND"`` or ``"OR"``.
        keyword_not: Exclusion terms for list path.
        search_in:   Comma-separated scope.  Valid: ``name``, ``description``,
                     ``readme``.  Default: ``"name,description"``.

    Returns:
        Keyword fragment ready to append to a GitHub Search query.
        Returns ``""`` for an empty list.

    Raises:
        ValueError: If ``keyword_op`` is invalid (list path).
        ValueError: If any token in ``search_in`` is invalid.

    Examples:
        >>> build_keyword_qualifier(["LLM"])
        '"LLM" in:name,description'
        >>> build_keyword_qualifier(["LLM", "agent"], keyword_op="AND")
        '"LLM" AND "agent" in:name,description'
        >>> ast = parse_boolean_query('(LLM OR GPT) AND agent AND NOT benchmark')
        >>> build_keyword_qualifier(ast)
        '("LLM" OR "GPT") AND "agent" AND NOT "benchmark" in:name,description'
    """
    _validate_search_in(search_in)

    # ── AST path ─────────────────────────────────────────────────────────────
    if isinstance(keywords, (Term, BoolNode)):
        body = _serialise_node(keywords)
        return f"{body} in:{search_in}"

    # ── list[str] path ────────────────────────────────────────────────────────
    if keyword_not is None:
        keyword_not = []

    op = keyword_op.strip().upper()
    if op not in VALID_KEYWORD_OPS:
        raise ValueError(
            f"Invalid keyword_op '{keyword_op}'. "
            f"Valid options: {sorted(VALID_KEYWORD_OPS)}"
        )

    clean = [kw.strip() for kw in keywords if kw.strip()]
    if not clean:
        return ""

    joined = f" {op} ".join(f'"{kw}"' for kw in clean)
    result = f"{joined} in:{search_in}"

    for term in keyword_not:
        t = term.strip()
        if t:
            result += f' NOT "{t}"'

    return result


# ──────────────────────────────────────────────
# Snapshot helpers
# ──────────────────────────────────────────────
def load_snapshots() -> dict:
    """
    Load previously saved star counts from disk.

    Returns:
        dict mapping repo full_name → {"stars": int, "saved_at": ISO string}.
        Empty dict if the file does not exist or is corrupted.
    """
    if not SNAPSHOT_FILE.exists():
        return {}
    try:
        return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(repos_by_category: dict) -> None:
    """
    Persist current star counts to disk, merging with existing data.

    Args:
        repos_by_category: output of search_trending_repos().
    """
    existing = load_snapshots()
    now = datetime.now(timezone.utc).isoformat()

    for repos in repos_by_category.values():
        for repo in repos:
            existing[repo["full_name"]] = {
                "stars": repo["stargazers_count"],
                "saved_at": now,
            }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def star_delta(repo: dict, snapshots: dict) -> int | None:
    """
    Calculate stars gained since the last snapshot (raw, not time-normalised).

    Args:
        repo:      repo dict from GitHub API.
        snapshots: loaded snapshot data.

    Returns:
        int delta, or None if no previous snapshot exists.

    Examples:
        >>> snapshots = {"owner/repo": {"stars": 12400, "saved_at": "..."}}
        >>> repo = {"full_name": "owner/repo", "stargazers_count": 12542}
        >>> star_delta(repo, snapshots)
        142
    """
    prev = snapshots.get(repo["full_name"])
    if prev is None:
        return None
    return repo["stargazers_count"] - prev["stars"]


def elapsed_days(snapshots: dict, full_name: str) -> float | None:
    """
    Return the number of days elapsed since the snapshot was saved.

    Args:
        snapshots:  loaded snapshot data.
        full_name:  repository full name, e.g. ``"owner/repo"``.

    Returns:
        Elapsed time in fractional days (always > 0), or ``None`` if the
        repo has no snapshot or ``saved_at`` is missing/unparseable.

    Examples:
        >>> from datetime import datetime, timezone, timedelta
        >>> ts = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        >>> snaps = {"owner/repo": {"stars": 100, "saved_at": ts}}
        >>> days = elapsed_days(snaps, "owner/repo")
        >>> 0.4 < days < 0.6
        True
    """
    entry = snapshots.get(full_name)
    if entry is None:
        return None
    saved_at_raw = entry.get("saved_at")
    if not saved_at_raw:
        return None
    try:
        saved_dt = datetime.fromisoformat(saved_at_raw)
        if saved_dt.tzinfo is None:
            saved_dt = saved_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_seconds = (now - saved_dt).total_seconds()
        return max(delta_seconds / 86400, 1 / 86400)
    except (ValueError, TypeError):
        return None


def daily_velocity(repo: dict, snapshots: dict) -> float | None:
    """
    Compute the time-normalised star growth rate in stars per day.

    Args:
        repo:      repo dict from GitHub API.
        snapshots: loaded snapshot data.

    Returns:
        Stars per day rounded to one decimal place, or ``None`` on first run.

    Examples:
        >>> from datetime import datetime, timezone, timedelta
        >>> ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        >>> snaps = {"owner/repo": {"stars": 12400, "saved_at": ts}}
        >>> repo = {"full_name": "owner/repo", "stargazers_count": 13100}
        >>> daily_velocity(repo, snaps)
        100.0
    """
    delta = star_delta(repo, snapshots)
    if delta is None:
        return None
    days = elapsed_days(snapshots, repo["full_name"])
    if days is None:
        return None
    return round(delta / days, 1)


# ──────────────────────────────────────────────
# Core search — repositories
# ──────────────────────────────────────────────
def search_trending_repos(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    keyword_not: list[str] | None = None,
    search_in: str = "name,description",
    bool_query: Union[Term, BoolNode, None] = None,
) -> dict:
    """
    Query the GitHub Search API and return top repositories by category.

    Three keyword input modes (mutually exclusive):

    1. ``keyword`` (str)  — single-term legacy path.
    2. ``keywords`` (list[str])  — multi-term boolean path via
       ``build_keyword_qualifier()``.
    3. ``bool_query`` (Term | BoolNode)  — pre-parsed AST path.
       ``build_keyword_qualifier()`` is called with the AST directly;
       ``search_in`` is honoured, ``keyword_op``/``keyword_not`` are
       ignored (model those inside the AST instead).

    Browse mode (no keyword input)
    ────────────────────────────────
    - New Today     — created today, >10 stars.
    - Active Giants — pushed today, >1000 stars.

    Search mode (any keyword input)
    ─────────────────────────────────
    - New & Relevant    — created recently, >50 stars.
    - Active & Relevant — pushed recently, >500 stars.

    Args:
        language:    Language filter (e.g. "python").
        since_days:  Days to look back (default: 1).
        top_n:       Max results per category (default: 10).
        keyword:     Single keyword string (legacy).
        keywords:    List of keyword terms for boolean search.
        keyword_op:  Connector for ``keywords``: ``"AND"`` or ``"OR"``.
        keyword_not: Exclusion terms for ``keywords`` path.
        search_in:   Comma-separated search scope.  Valid: ``name``,
                     ``description``, ``readme``.  Default:
                     ``"name,description"``.
        bool_query:  Pre-parsed AST from ``parse_boolean_query()``.  When
                     provided, ``keyword_op`` and ``keyword_not`` are ignored.

    Returns:
        dict: {category_label: [repo_dict, ...]}

    Raises:
        ValueError: If more than one keyword input mode is active.
        ValueError: If any token in ``search_in`` is invalid.
        ValueError: If ``keyword_op`` is not ``"AND"`` or ``"OR"``.
        requests.HTTPError, requests.ConnectionError, requests.Timeout
    """
    # Guard: at most one keyword mode active
    active_modes = sum([
        keyword is not None,
        bool(keywords),
        bool_query is not None,
    ])
    if active_modes > 1:
        raise ValueError(
            "'keyword', 'keywords', and 'bool_query' are mutually exclusive."
        )

    _validate_search_in(search_in)

    since_date = (date.today() - timedelta(days=since_days)).isoformat()

    # ── Build keyword qualifier ───────────────────────────────────────────────
    if bool_query is not None:
        # AST path — search_in honoured, keyword_op/keyword_not ignored
        keyword_qualifier = " " + build_keyword_qualifier(
            bool_query, search_in=search_in
        )
        is_search_mode = True

    elif keywords is not None:
        # Multi-keyword list path
        keyword_qualifier = (
            " " + build_keyword_qualifier(
                keywords,
                keyword_op=keyword_op,
                keyword_not=keyword_not or [],
                search_in=search_in,
            )
            if keywords
            else ""
        )
        is_search_mode = bool(keywords)

    else:
        # Legacy single-keyword path
        keyword_qualifier = f' "{keyword}" in:{search_in}' if keyword else ""
        is_search_mode = bool(keyword)

    if is_search_mode:
        queries = {
            "New & Relevant": f"created:>={since_date} stars:>50{keyword_qualifier}",
            "Active & Relevant": f"pushed:>={since_date} stars:>500{keyword_qualifier}",
        }
    else:
        queries = {
            "New Today": f"created:>={since_date} stars:>10",
            "Active Giants": f"pushed:>={since_date} stars:>1000",
        }

    if language:
        queries = {k: v + f" language:{language}" for k, v in queries.items()}

    results: dict = {}
    seen_ids: set = set()

    for label, query in queries.items():
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=get_headers(),
            params={"q": query, "sort": "stars", "order": "desc", "per_page": top_n},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        unique = [r for r in items if r["id"] not in seen_ids]
        seen_ids.update(r["id"] for r in unique)
        results[label] = unique

    return results


# ──────────────────────────────────────────────
# Core search — developers
# ──────────────────────────────────────────────
def search_trending_developers(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
) -> list[dict]:
    """
    Query the GitHub Search API and return top active developers.

    Two complementary strategies:
    - Rising Stars    — accounts created recently with public repos.
    - Active Veterans — established developers with high follower counts.

    Each developer is enriched with one extra ``/users/{login}`` request.

    Args:
        language:   Language filter.
        since_days: Days to look back for rising stars (default: 1).
        top_n:      Max developers to return (default: 10).

    Returns:
        list of enriched user dicts.

    Raises:
        requests.HTTPError, requests.ConnectionError, requests.Timeout
    """
    since_date = (date.today() - timedelta(days=since_days)).isoformat()
    lang_qualifier = f" language:{language}" if language else ""

    queries = [
        f"created:>={since_date} repos:>0 followers:>0{lang_qualifier}",
        f"followers:>100{lang_qualifier}",
    ]

    seen_logins: set = set()
    raw_users: list = []

    for query in queries:
        if len(raw_users) >= top_n:
            break
        resp = requests.get(
            "https://api.github.com/search/users",
            headers=get_headers(),
            params={"q": query, "sort": "followers", "order": "desc", "per_page": top_n},
            timeout=15,
        )
        resp.raise_for_status()
        for user in resp.json().get("items", []):
            if user["login"] not in seen_logins:
                seen_logins.add(user["login"])
                raw_users.append(user)
            if len(raw_users) >= top_n:
                break

    enriched: list[dict] = []
    for user in raw_users[:top_n]:
        try:
            detail_resp = requests.get(
                f"https://api.github.com/users/{user['login']}",
                headers=get_headers(),
                timeout=15,
            )
            detail_resp.raise_for_status()
            enriched.append(detail_resp.json())
        except requests.RequestException:
            enriched.append(user)

    return enriched


# ──────────────────────────────────────────────
# Export helpers — repositories
# ──────────────────────────────────────────────
def build_export_row(repo: dict, rank: int, category: str, snapshots: dict) -> dict:
    """
    Build a flat export record from a repo dict.

    Args:
        repo:      repo dict from GitHub API.
        rank:      1-based rank within its category.
        category:  category label.
        snapshots: loaded snapshot data.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    delta = star_delta(repo, snapshots)
    velocity = daily_velocity(repo, snapshots)
    return {
        "rank":           rank,
        "category":       category,
        "full_name":      repo["full_name"],
        "stars":          repo["stargazers_count"],
        "star_delta":     delta,
        "daily_velocity": velocity,
        "forks":          repo["forks_count"],
        "language":       repo.get("language") or "",
        "description":    (repo.get("description") or "").replace("\n", " "),
        "created_at":     repo["created_at"][:10],
        "updated_at":     repo["updated_at"][:10],
        "url":            repo["html_url"],
    }


# ──────────────────────────────────────────────
# Export helpers — developers
# ──────────────────────────────────────────────
def build_dev_export_row(user: dict, rank: int) -> dict:
    """
    Build a flat export record from an enriched user dict.

    Args:
        user: enriched user dict.
        rank: 1-based display rank.

    Returns:
        Ordered dict suitable for JSON serialisation or csv.DictWriter.
    """
    return {
        "rank":         rank,
        "login":        user.get("login") or "",
        "name":         user.get("name") or "",
        "company":      (user.get("company") or "").strip().lstrip("@"),
        "location":     user.get("location") or "",
        "public_repos": user.get("public_repos") or 0,
        "followers":    user.get("followers") or 0,
        "following":    user.get("following") or 0,
        "url":          user.get("html_url") or "",
    }


def export_json(rows: list[dict]) -> str:
    """Serialise export rows to a pretty-printed JSON string."""
    return json.dumps(rows, indent=2, ensure_ascii=False)


def export_csv(rows: list[dict], fieldnames: list[str]) -> str:
    """
    Serialise export rows to a CSV string (utf-8-sig for Excel compat).

    ``None`` values are written as empty strings.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()


def write_output(content: str, output_file: str | None, fmt: str) -> None:
    """
    Write export content to a file or stdout.

    Args:
        content:     String content to write.
        output_file: File path, or None to write to stdout.
        fmt:         Format label for the confirmation message.
    """
    if output_file:
        encoding = "utf-8-sig" if fmt == "csv" else "utf-8"
        Path(output_file).write_text(content, encoding=encoding)
        print(f"  Exported {fmt.upper()} → {output_file}", file=sys.stderr)
    else:
        print(content)


# ──────────────────────────────────────────────
# Text formatting (human-readable)
# ──────────────────────────────────────────────
def format_velocity(delta: int | None, velocity: float | None = None) -> str:
    """
    Render star delta and daily velocity as a human-readable badge.

    Examples:
        >>> format_velocity(None, None)
        '  Δ  — (first run — no velocity data yet)'
        >>> format_velocity(700, 100.0)
        '  Δ +700 ⭐ total  |  ~100.0 ⭐/day'
        >>> format_velocity(142)
        '  Δ +142 ⭐'
    """
    if delta is None:
        return "  Δ  — (first run — no velocity data yet)"
    sign = "+" if delta > 0 else ""
    if velocity is None:
        return f"  Δ {sign}{delta:,} ⭐"
    return f"  Δ {sign}{delta:,} ⭐ total  |  ~{velocity:,} ⭐/day"


def format_repo(repo: dict, rank: int, snapshots: dict) -> str:
    """Format a single repo dict into a human-readable terminal block."""
    delta = star_delta(repo, snapshots)
    velocity = daily_velocity(repo, snapshots)
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {repo['full_name']}\n"
        f"    Stars: {repo['stargazers_count']:,}  "
        f"Forks: {repo['forks_count']:,}  "
        f"Lang: {repo.get('language') or 'N/A'}\n"
        f"{format_velocity(delta, velocity)}\n"
        f"    Created: {repo['created_at'][:10]}  |  Updated: {repo['updated_at'][:10]}\n"
        f"    {(repo.get('description') or 'No description')[:80]}\n"
        f"    {repo['html_url']}\n"
    )


def format_developer(user: dict, rank: int) -> str:
    """Format a single enriched user dict into a human-readable terminal block."""
    name = user.get("name") or user.get("login", "")
    company = (user.get("company") or "").strip().lstrip("@")
    location = user.get("location") or "N/A"
    bio = (user.get("bio") or "No bio")[:80]
    return (
        f"{'=' * 70}\n"
        f"#{rank}  {user.get('login', '')}  ({name})\n"
        f"    Followers: {user.get('followers', 0):,}  "
        f"Repos: {user.get('public_repos', 0):,}  "
        f"Following: {user.get('following', 0):,}\n"
        f"    Company : {company or 'N/A'}\n"
        f"    Location: {location}\n"
        f"    {bio}\n"
        f"    {user.get('html_url', '')}\n"
    )


# ──────────────────────────────────────────────
# Entry point — repositories
# ──────────────────────────────────────────────
def find_repo_of_the_day(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    keyword: str | None = None,
    keywords: list[str] | None = None,
    keyword_op: str = "AND",
    keyword_not: list[str] | None = None,
    search_in: str = "name,description",
    bool_query: Union[Term, BoolNode, None] = None,
    use_snapshots: bool = True,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
    wildcard: bool = False,
) -> None:
    """
    Fetch, display/export, and optionally snapshot the top repos of the day.

    Three keyword input modes (mutually exclusive):

    1. ``keyword`` (str)  — single-term legacy path.
    2. ``keywords`` (list[str])  — multi-term boolean path.
       ``wildcard=True`` expands ``?``/``*`` patterns before querying.
    3. ``bool_query`` (Term | BoolNode)  — pre-parsed AST passed directly
       to ``search_trending_repos()``; ``search_in`` is honoured.
       Future: wildcard expansion across AST leaf terms.

    Orchestration order:
      1. Print session header (text mode only).
      2. Apply wildcard expansion to keywords (if wildcard=True).
      3. Load previous snapshot (if use_snapshots).
      4. Fetch repos via search_trending_repos().
      5. Render output in the requested format.
      6. Save new snapshot baseline (if use_snapshots).

    Args:
        language:      Language filter.
        since_days:    Days to look back.
        top_n:         Repos per category.
        keyword:       Single keyword (legacy).
        keywords:      List of keywords for boolean search.
        keyword_op:    Connector for keywords: AND (default) or OR.
        keyword_not:   Exclusion terms.
        search_in:     Search scope. Default: ``"name,description"``.
        bool_query:    Pre-parsed AST from ``parse_boolean_query()``.
        use_snapshots: Load/save velocity snapshots.
        output_fmt:    Output format: "text", "json", or "csv".
        output_file:   Write output to this path instead of stdout.
        wildcard:      Expand ? and * patterns in keywords via NLTK.

    Raises:
        SystemExit(1): On GitHub API errors.
    """
    # Wildcard expansion (keywords path only for now)
    if wildcard and keywords:
        keywords = apply_wildcards_to_keywords(keywords)

    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        if language:
            print(f"  Language : {language}")
        if bool_query is not None:
            print(f"  Query    : {_serialise_node(bool_query)}  in [{search_in}]")
        elif keywords:
            op_label = keyword_op.upper()
            kw_display = f" {op_label} ".join(keywords)
            print(f"  Keywords : {kw_display}  in [{search_in}]")
            if keyword_not:
                print(f"  Exclude  : {', '.join(keyword_not)}")
        elif keyword:
            print(f"  Keyword  : '{keyword}'  in [{search_in}]")
        auth = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
        print(f"  Auth     : {auth}")
        snap_status = "enabled" if use_snapshots else "disabled (--no-snapshot)"
        print(f"  Velocity : {snap_status}")
        if wildcard:
            print(f"  Wildcard : enabled")
        print(f"{'#' * 70}\n")

    snapshots = load_snapshots() if use_snapshots else {}

    try:
        all_results = search_trending_repos(
            language=language,
            since_days=since_days,
            top_n=top_n,
            keyword=keyword,
            keywords=keywords,
            keyword_op=keyword_op,
            keyword_not=keyword_not,
            search_in=search_in,
            bool_query=bool_query,
        )
    except requests.HTTPError as exc:
        print(f"[ERROR] GitHub API returned: {exc}", file=sys.stderr)
        if not GITHUB_TOKEN:
            print("  Tip: set GITHUB_TOKEN in .env to raise rate limit to 5,000 req/hr.",
                  file=sys.stderr)
        sys.exit(1)
    except requests.ConnectionError:
        print("[ERROR] Could not reach GitHub API. Check your internet connection.",
              file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print("[ERROR] GitHub API request timed out. Try again in a moment.",
              file=sys.stderr)
        sys.exit(1)

    if output_fmt == "text":
        for category, repos in all_results.items():
            print(f"\n{'─' * 70}")
            print(f"  {category}")
            print(f"{'─' * 70}")
            if not repos:
                print("  No repositories found.\n")
                continue
            for i, repo in enumerate(repos, 1):
                print(format_repo(repo, i, snapshots))
    else:
        rows: list[dict] = []
        for category, repos in all_results.items():
            for i, repo in enumerate(repos, 1):
                rows.append(build_export_row(repo, i, category, snapshots))
        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows, EXPORT_FIELDS), output_file, "csv")

    if use_snapshots:
        save_snapshots(all_results)
        if output_fmt == "text":
            print(f"\n  Snapshot saved → {SNAPSHOT_FILE}")
        else:
            print(f"  Snapshot saved → {SNAPSHOT_FILE}", file=sys.stderr)


# ──────────────────────────────────────────────
# Entry point — developers
# ──────────────────────────────────────────────
def find_developer_of_the_day(
    language: str | None = None,
    since_days: int = 1,
    top_n: int = 10,
    output_fmt: Literal["text", "json", "csv"] = "text",
    output_file: str | None = None,
) -> None:
    """
    Fetch and display/export the top trending developers of the day.

    Args:
        language:    Language filter.
        since_days:  Days to look back for rising stars.
        top_n:       Developers to show.
        output_fmt:  Output format: "text", "json", or "csv".
        output_file: Write output to this path instead of stdout.

    Raises:
        SystemExit(1): On GitHub API errors.
    """
    if output_fmt == "text":
        print(f"\n{'#' * 70}")
        print(f"  daily-github-pulse v{VERSION}  —  {date.today().isoformat()}")
        print(f"  Mode     : Trending Developers")
        if language:
            print(f"  Language : {language}")
        auth = "Authenticated" if GITHUB_TOKEN else "Unauthenticated (60 req/hr limit)"
        print(f"  Auth     : {auth}")
        print(f"{'#' * 70}\n")

    try:
        developers = search_trending_developers(
            language=language,
            since_days=since_days,
            top_n=top_n,
        )
    except requests.HTTPError as exc:
        print(f"[ERROR] GitHub API returned: {exc}", file=sys.stderr)
        if not GITHUB_TOKEN:
            print("  Tip: set GITHUB_TOKEN in .env to raise rate limit to 5,000 req/hr.",
                  file=sys.stderr)
        sys.exit(1)
    except requests.ConnectionError:
        print("[ERROR] Could not reach GitHub API. Check your internet connection.",
              file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print("[ERROR] GitHub API request timed out. Try again in a moment.",
              file=sys.stderr)
        sys.exit(1)

    if output_fmt == "text":
        print(f"\n{'─' * 70}")
        print(f"  Trending Developers")
        print(f"{'─' * 70}")
        if not developers:
            print("  No developers found.\n")
        else:
            for i, user in enumerate(developers, 1):
                print(format_developer(user, i))
    else:
        rows = [build_dev_export_row(u, i) for i, u in enumerate(developers, 1)]
        if output_fmt == "json":
            write_output(export_json(rows), output_file, "json")
        elif output_fmt == "csv":
            write_output(export_csv(rows, DEV_EXPORT_FIELDS), output_file, "csv")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="daily-github-pulse",
        description="Find GitHub top repos and developers of the day.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: today's top repos, all languages
  python github_repo_of_the_day.py

  # Trending developers
  python github_repo_of_the_day.py --developers

  # Named period shortcut
  python github_repo_of_the_day.py --period week

  # Top Python repos
  python github_repo_of_the_day.py --language python

  # Export as CSV
  python github_repo_of_the_day.py --output csv --output-file results.csv

  # Single keyword search (legacy)
  python github_repo_of_the_day.py --keyword "LLM agent"

  # Multi-keyword AND search
  python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

  # Multi-keyword with exclusions
  python github_repo_of_the_day.py --keywords LLM agent --keyword-not benchmark survey

  # Full Boolean query (dedicated AST path, search_in honoured)
  python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'
  python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent' --search-in name,description,readme

  # Wildcard expansion
  python github_repo_of_the_day.py --keywords "analy?e" --wildcard
  python github_repo_of_the_day.py --keywords "optimiz*" agent --wildcard

  # Search in README too
  python github_repo_of_the_day.py --keywords MCP server --search-in name,description,readme

Token setup:
  cp .env.example .env  # then set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
  Get a token: https://github.com/settings/tokens

Wildcard setup (one-time):
  pip install nltk
  # corpus downloads automatically on first --wildcard run
        """,
    )

    parser.add_argument("--developers", "--devs", action="store_true",
                        help="Show trending developers instead of repositories.")
    parser.add_argument("--language", "-l", metavar="LANG",
                        help="Filter by language (e.g. python, go, rust)")
    parser.add_argument("--period", "-p", choices=["day", "week", "month"],
                        metavar="PERIOD",
                        help="Named look-back window: day (1), week (7), month (30).")
    parser.add_argument("--days", "-d", type=int, default=1, metavar="N",
                        help="Look back N days (default: 1). Ignored when --period is used.")
    parser.add_argument("--top", "-n", type=int, default=10, metavar="N",
                        help="Results per category (default: 10)")
    parser.add_argument("--token", "-t", metavar="TOKEN",
                        help="GitHub PAT — overrides .env")
    parser.add_argument("--keyword", "-k", metavar="WORD",
                        help="Single keyword search (legacy). "
                             "Mutually exclusive with --keywords and --bool-query.")
    parser.add_argument("--keywords", nargs="+", metavar="WORD",
                        help="Multi-keyword boolean search. "
                             "Mutually exclusive with --keyword and --bool-query.")
    parser.add_argument("--bool-query", metavar="EXPR",
                        help="Full Boolean expression: '(LLM OR GPT) AND agent AND NOT benchmark'. "
                             "Parsed into AST and sent through dedicated path. "
                             "Mutually exclusive with --keyword and --keywords.")
    parser.add_argument("--keyword-op", default="AND", metavar="OP",
                        choices=["AND", "OR", "and", "or"],
                        help="Connector for --keywords: AND (default) or OR.")
    parser.add_argument("--keyword-not", nargs="+", metavar="WORD",
                        help="Terms to exclude (NOT clause). Used with --keywords.")
    parser.add_argument("--search-in", "-s", default="name,description", metavar="SCOPE",
                        help="Search scope: name, description, readme "
                             "(comma-separated, default: name,description). "
                             "Honoured by all three keyword modes.")
    parser.add_argument("--wildcard", action="store_true",
                        help="Expand ? and * in --keywords via NLTK corpus. "
                             "Requires: pip install nltk")
    parser.add_argument("--output", "-o", choices=["text", "json", "csv"],
                        default="text", metavar="FORMAT",
                        help="Output format: text (default), json, csv")
    parser.add_argument("--output-file", "-f", metavar="FILE",
                        help="Write output to FILE instead of stdout")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="Disable snapshot save/load for this run")
    parser.add_argument("--clear-snapshots", action="store_true",
                        help=f"Delete all stored snapshots and exit ({SNAPSHOT_FILE})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()

    if args.token:
        GITHUB_TOKEN = args.token

    if args.clear_snapshots:
        if SNAPSHOT_FILE.exists():
            SNAPSHOT_FILE.unlink()
            print(f"Snapshots cleared: {SNAPSHOT_FILE}")
        else:
            print("No snapshot file found.")
        sys.exit(0)

    # Validate mutually exclusive keyword flags
    active_kw_flags = sum([
        args.keyword is not None,
        bool(getattr(args, "keywords", None)),
        bool(getattr(args, "bool_query", None)),
    ])
    if active_kw_flags > 1:
        parser.error("--keyword, --keywords, and --bool-query are mutually exclusive.")

    effective_days = resolve_period(args.period, args.days)

    # Parse --bool-query into AST here; pass AST down — no string conversion
    bool_query_ast: Union[Term, BoolNode, None] = None
    if getattr(args, "bool_query", None):
        bool_query_ast = parse_boolean_query(args.bool_query)

    if args.developers:
        find_developer_of_the_day(
            language=args.language,
            since_days=effective_days,
            top_n=args.top,
            output_fmt=args.output,
            output_file=args.output_file,
        )
    else:
        find_repo_of_the_day(
            language=args.language,
            since_days=effective_days,
            top_n=args.top,
            keyword=args.keyword,
            keywords=args.keywords,
            keyword_op=args.keyword_op,
            keyword_not=args.keyword_not,
            search_in=args.search_in,
            bool_query=bool_query_ast,
            use_snapshots=not args.no_snapshot,
            output_fmt=args.output,
            output_file=args.output_file,
            wildcard=args.wildcard,
        )
