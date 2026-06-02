# daily-github-pulse

[![CI](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml)

Discover GitHub's trending repositories and developers — with real star
velocity tracking.

---

## Features

- **Two-strategy repo search** — *New Today* (recently created) and *Active
  Giants* (recently pushed) in browse mode; *New & Relevant* and
  *Active & Relevant* in keyword/search mode.
- **Star velocity** — raw delta (stars gained since last run) **and**
  time-normalised rate (⭐/day), so the number stays meaningful even if
  you haven't run the tool in days.
- **Multi-keyword boolean search** — combine multiple keywords with `AND`
  or `OR`, exclude noisy terms with `NOT`.
- **Developer discovery** — Rising Stars and Active Veterans, enriched with
  full profile data.
- **Flexible output** — human-readable text, JSON, or CSV.
- **Language filter** — narrow results to any GitHub-recognised language.
- **Named time windows** — `--period day/week/month` shorthand.
- **GitHub token support** — via `--token`, `.env`, or `GITHUB_TOKEN` env var.

---

## Quick Start

```bash
pip install requests python-dotenv
python github_repo_of_the_day.py
```

---

## Usage

### Repository search

```bash
# Browse mode — today's trending repos (all languages)
python github_repo_of_the_day.py

# Language filter
python github_repo_of_the_day.py --language python

# Named time window
python github_repo_of_the_day.py --period week
python github_repo_of_the_day.py --period month --language rust

# Single keyword (legacy)
python github_repo_of_the_day.py --keyword "LLM agent"

# Multi-keyword AND (both terms must match)
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# Multi-keyword OR (either term matches)
python github_repo_of_the_day.py --keywords LLM GPT Claude --keyword-op OR

# Exclude noisy terms
python github_repo_of_the_day.py --keywords LLM agent --keyword-not benchmark survey

# Search in README too (slower)
python github_repo_of_the_day.py --keywords MCP server --search-in name,description,readme

# JSON export
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND --output json

# CSV to file
python github_repo_of_the_day.py --output csv --output-file results.csv
```

### Developer search

```bash
# Trending developers (all languages)
python github_repo_of_the_day.py --developers

# Trending Python developers
python github_repo_of_the_day.py --developers --language python

# JSON export
python github_repo_of_the_day.py --developers --output json
```

### Snapshot / velocity

```bash
# Skip velocity tracking for this run
python github_repo_of_the_day.py --no-snapshot

# Reset all stored snapshots
python github_repo_of_the_day.py --clear-snapshots
```

---

## CLI Reference

| Flag | Short | Default | Description |
|---|---|---|---|
| `--developers` | | `False` | Show trending developers instead of repos |
| `--language` | `-l` | — | Filter by programming language |
| `--period` | `-p` | — | `day` / `week` / `month` shorthand |
| `--days` | `-d` | `1` | Look-back window in days (ignored if `--period` set) |
| `--top` | `-n` | `10` | Results per category |
| `--token` | `-t` | — | GitHub PAT (overrides `.env`) |
| `--keyword` | `-k` | — | Single keyword (legacy; mutually exclusive with `--keywords`) |
| `--keywords` | | — | One or more keywords for boolean search |
| `--keyword-op` | | `AND` | Connector between `--keywords`: `AND` or `OR` |
| `--keyword-not` | | — | Terms to exclude (`NOT` clauses) |
| `--search-in` | `-s` | `name,description` | Search scope: `name`, `description`, `readme` |
| `--output` | `-o` | `text` | Output format: `text`, `json`, `csv` |
| `--output-file` | `-f` | — | Write output to file instead of stdout |
| `--no-snapshot` | | `False` | Disable snapshot for this run |
| `--clear-snapshots` | | — | Delete all snapshots and exit |
| `--version` | | — | Print version and exit |

---

## Multi-Keyword Boolean Search

The `--keywords` flag accepts one or more terms and composes a GitHub Search
query fragment:

| Command | GitHub query fragment |
|---|---|
| `--keywords LLM` | `"LLM" in:name,description` |
| `--keywords LLM agent --keyword-op AND` | `"LLM" AND "agent" in:name,description` |
| `--keywords LLM GPT --keyword-op OR` | `"LLM" OR "GPT" in:name,description` |
| `--keywords LLM agent --keyword-not benchmark` | `"LLM" AND "agent" in:name,description NOT "benchmark"` |

**Rules:**
- Each term is quoted → multi-word phrases match as exact phrases.
- `in:` scope is appended **once**, not once per term.
- `--keyword-not` terms are appended as `NOT "term"` after the positive block.
- `--keywords` and `--keyword` are mutually exclusive.
- `--keywords` (empty) → browse mode.

---

## How Velocity Works

On each run, star counts are saved to `~/.daily-github-pulse/snapshots.json`.
On the next run:

- **star_delta** — raw difference since last snapshot.
- **daily_velocity** — time-normalised rate: `star_delta ÷ elapsed_days`,
  rounded to one decimal place. A repo that gained 1 400 stars over 14 days
  reports `100.0 ⭐/day`, the same as one that gained 100 stars today.

---

## Auth & Rate Limits

| Mode | Rate limit |
|---|---|
| Unauthenticated | 60 requests / hour |
| Authenticated (PAT) | 5,000 requests / hour |

Create a `.env` file in the project root:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

Add `.env` to `.gitignore`. Get a token at
https://github.com/settings/tokens (no scopes needed for public search).

---

## CI

Every push and pull request to `main` runs the full test suite across
Python 3.9 – 3.14 via GitHub Actions.

To enable Telegram notifications, add two repository secrets:
- `TELEGRAM_BOT_TOKEN` — your bot token from @BotFather
- `TELEGRAM_CHAT_ID` — your chat / channel ID

The `notify` job skips silently if the secrets are absent.

---

## Python API

```python
from github_repo_of_the_day import (
    build_keyword_qualifier,
    search_trending_repos,
    find_repo_of_the_day,
)

# Build a query fragment manually
q = build_keyword_qualifier(
    ["LLM", "agent"],
    keyword_op="AND",
    keyword_not=["benchmark"],
    search_in="name,description",
)
# '"LLM" AND "agent" in:name,description NOT "benchmark"'

# Boolean OR search
results = search_trending_repos(
    keywords=["LLM", "GPT", "Claude"],
    keyword_op="OR",
    since_days=7,
    language="python",
)

# With exclusions
results = search_trending_repos(
    keywords=["LLM", "agent"],
    keyword_op="AND",
    keyword_not=["benchmark", "survey"],
)

# High-level entry point
find_repo_of_the_day(
    keywords=["MCP", "server"],
    keyword_op="AND",
    keyword_not=["deprecated"],
    language="python",
    since_days=7,
    output_fmt="json",
)
```

---

## License

MIT
