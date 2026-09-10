"""Boolean keyword search: AST nodes, parser, and qualifier builder."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

VALID_SEARCH_IN = {"name", "description", "readme"}
VALID_KEYWORD_OPS = {"AND", "OR"}


@dataclass(frozen=True, eq=True)
class Term:
    """
    A single search term, optionally negated.

    Attributes:
        value:   The raw term string (stripped of surrounding quotes).
        negated: True when this term was preceded by NOT.
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
    """

    op: str
    children: list[Union["Term", "BoolNode"]] = field(default_factory=list)


_TOKEN_RE = re.compile(
    r'"[^"]*"'
    r"|\("
    r"|\)"
    r'|[^\s()"]+',
    re.IGNORECASE,
)


def _tokenise(expr: str) -> list[str]:
    """Split expression into a flat token list."""
    return _TOKEN_RE.findall(expr)


def _parse_expr(
    tokens: list[str], pos: int, inside_group: bool = False
) -> tuple[Union[Term, BoolNode], int]:
    """Parse tokens[pos:] into an AST node. Returns ``(node, new_pos)``."""
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


def parse_boolean_query(expr: str) -> Union[Term, BoolNode]:
    """
    Parse a Boolean keyword expression into an AST.

    Args:
        expr: Boolean keyword string, e.g. ``'(LLM OR GPT) AND agent'``.

    Returns:
        A ``Term`` or ``BoolNode``.

    Raises:
        ValueError: Empty expression, unbalanced parentheses, missing
            operators, or dangling operators.

    Examples:
        >>> parse_boolean_query("LLM")
        Term(value='LLM', negated=False)
        >>> parse_boolean_query("LLM AND agent")
        BoolNode(op='AND', children=[Term(value='LLM', ...), Term(value='agent', ...)])
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
    """Serialise a Term or BoolNode to a Search query fragment."""
    if isinstance(node, Term):
        quoted = f'"{node.value}"'
        return f"NOT {quoted}" if node.negated else quoted

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
    Build the keyword fragment of a forge search query string.

    Args:
        keywords:    ``list[str]``, a ``Term``, or a ``BoolNode``.
        keyword_op:  Connector for list path: ``"AND"`` or ``"OR"``.
        keyword_not: Exclusion terms for list path.
        search_in:   Comma-separated scope fields.

    Returns:
        Keyword fragment ready to append to a search query.

    Raises:
        ValueError: Invalid ``keyword_op`` or ``search_in`` tokens.

    Examples:
        >>> build_keyword_qualifier(["LLM"])
        '"LLM" in:name,description'
    """
    _validate_search_in(search_in)

    if isinstance(keywords, (Term, BoolNode)):
        body = _serialise_node(keywords)
        return f"{body} in:{search_in}"

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


def _load_wordlist() -> set[str] | None:
    """Load the NLTK words corpus as a lower-cased set, or None."""
    try:
        import nltk  # type: ignore
        from nltk.corpus import words as nltk_words  # type: ignore

        try:
            return set(w.lower() for w in nltk_words.words())
        except LookupError:
            nltk.download("words", quiet=True)
            return set(w.lower() for w in nltk_words.words())
    except ImportError:
        return None


def expand_wildcards(
    term: str,
    wordlist: set[str] | None = None,
    max_variants: int = 20,
) -> list[str]:
    """
    Expand a wildcard term into matching English words.

    Args:
        term:         Keyword that may contain ``?`` and/or ``*``.
        wordlist:     Optional pre-loaded word set.
        max_variants: Upper bound on variants (default 20).

    Returns:
        Matching words, or ``[term]`` when no expansion applies.
    """
    if "?" not in term and "*" not in term:
        return [term]

    if wordlist is None:
        wordlist = _load_wordlist()

    if wordlist is None:
        return [term]

    escaped = re.escape(term)
    pattern = escaped.replace(re.escape("?"), r".").replace(re.escape("*"), r".*")
    regex = re.compile(r"^" + pattern + r"$", re.IGNORECASE)

    matches = sorted({w for w in wordlist if regex.match(w)})[:max_variants]
    return matches if matches else [term]


def apply_wildcards_to_keywords(
    keywords: list[str],
    wordlist: set[str] | None = None,
) -> list[str]:
    """
    Expand wildcard patterns inside a keyword list.

    Args:
        keywords: Raw keyword strings.
        wordlist: Optional pre-loaded word set.

    Returns:
        New list with wildcard terms replaced by ``(a OR b OR ...)``.
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
