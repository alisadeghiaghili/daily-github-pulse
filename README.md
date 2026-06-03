# daily-github-pulse

> Discover GitHub's top trending repositories and developers of the day — with real star velocity, boolean keyword search, wildcard expansion, and AI relevance filtering.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Tests](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Features

| Feature | Flag | Notes |
|---|---|---|
| Browse trending repos | _(default)_ | New Today + Active Giants |
| Trending developers | `--developers` | Rising Stars + Active Veterans |
| Language filter | `-l` / `--language python` | Any GitHub language slug |
| Look-back period | `-p` / `--period week` | `day` / `week` / `month` |
| Custom day range | `-d` / `--days N` | Overridden by `--period` |
| Result count | `-n` / `--top N` | Per category, default: 10 |
| Single keyword | `-k` / `--keyword "LLM agent"` | Searches name + description |
| Multi-keyword boolean | `--keywords LLM agent` | AND / OR via `--keyword-op` |
| Full boolean expression | `--bool-query '(LLM OR GPT) AND agent'` | Supports NOT and parentheses |
| Exclusion terms | `--keyword-not benchmark survey` | Appends `NOT "term"` clauses |
| Wildcard expansion | `--wildcard` | `analy?e` → `analyse OR analyze` |
| Search scope | `-s` / `--search-in name,description,readme` | `readme` is slower |
| GitHub token | `-t` / `--token TOKEN` | Overrides `.env` |
| Star velocity | _(auto)_ | Stars/day, time-normalised |
| Skip snapshot | `--no-snapshot` | Disables velocity I/O |
| Reset snapshots | `--clear-snapshots` | Deletes snapshot file |
| Export format | `-o` / `--output json/csv` | Pipe-friendly |
| Export to file | `-f` / `--output-file results.csv` | json or csv |
| AI relevance filter | `--ai-filter "your intent"` | LLM post-filters results |
| AI fallback policy | `--ai-filter-fallback passthrough` | `fail` (default) or `passthrough` |

---

## Installation

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt

# Optional: wildcard expansion
pip install nltk

# Optional: AI relevance filter (OpenAI-compatible)
pip install requests  # already in requirements

# Optional: AI relevance filter (Anthropic)
pip install anthropic

# Recommended: add your GitHub token
cp .env.example .env
# Edit .env and set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

---

## Quick Start

```bash
# Today's top repos (all languages)
python github_repo_of_the_day.py

# Top Python repos this week
python github_repo_of_the_day.py -l python -p week

# Search for LLM + agent repos
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# Full boolean query
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'

# Wildcard: analy?e → analyse OR analyze
python github_repo_of_the_day.py --keywords "analy?e" --wildcard

# Trending developers
python github_repo_of_the_day.py --developers -l python

# Export as CSV
python github_repo_of_the_day.py -l go -o csv -f results.csv
```

---

## Keyword Search

### Single keyword (legacy)

```bash
python github_repo_of_the_day.py -k "vector database"
python github_repo_of_the_day.py --keyword "LLM agent"
```

### Multi-keyword with boolean operator

```bash
# AND: both terms must appear
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# OR: either term
python github_repo_of_the_day.py --keywords LLM GPT Claude --keyword-op OR

# With exclusions
python github_repo_of_the_day.py --keywords LLM agent --keyword-not benchmark survey
```

### Full boolean expression

```bash
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'
python github_repo_of_the_day.py --bool-query '"large language model" AND NOT survey' --search-in name,description,readme
```

Supported syntax:

| Syntax | Meaning | Example |
|---|---|---|
| `A AND B` | Both terms must appear | `LLM AND agent` |
| `A OR B` | Either term must appear | `LLM OR GPT` |
| `NOT A` | Exclude term | `NOT benchmark` |
| `(A OR B) AND C` | Parentheses for grouping | `(LLM OR GPT) AND agent` |
| `"multi word"` | Quoted phrase as one term | `"large language model"` |

Operators are case-insensitive (`and`, `AND`, `And` are all valid).

### Wildcard expansion

Requires `pip install nltk` (corpus auto-downloaded on first use).

```bash
# ? = exactly one character
python github_repo_of_the_day.py --keywords "analy?e" --wildcard
# → query includes: (analyse OR analyze)

# * = zero or more characters
python github_repo_of_the_day.py --keywords "optimiz*" agent --wildcard
# → query includes: (optimize OR optimized OR optimizes OR optimizing ...) AND agent
```

> **Without `nltk`:** `--wildcard` is a no-op — terms pass through unchanged. No crash.

### Search scope

```bash
# Search name and description only (default)
python github_repo_of_the_day.py --keywords MCP server

# Also search README (slower — one extra API call per page)
python github_repo_of_the_day.py --keywords MCP server -s name,description,readme
```

Valid scope tokens: `name`, `description`, `readme` (comma-separated, any combination).

---

## Star Velocity

On each run, star counts are saved to `~/.daily-github-pulse/snapshots.json`. On subsequent runs, two velocity numbers are shown:

- **Δ raw** — total stars gained since last snapshot
- **~N ⭐/day** — time-normalised daily rate (stays meaningful even after long gaps)

```
  Δ +1,400 ⭐ total  |  ~200.0 ⭐/day
```

```bash
# Skip snapshot I/O for this run
python github_repo_of_the_day.py --no-snapshot

# Delete all stored snapshots
python github_repo_of_the_day.py --clear-snapshots
```

---

## Export

```bash
# JSON to stdout (pipe into jq)
python github_repo_of_the_day.py -o json | jq '.[].full_name'

# CSV to file
python github_repo_of_the_day.py -o csv -f results.csv

# Developers as JSON
python github_repo_of_the_day.py --developers -o json

# Keyword search exported to JSON
python github_repo_of_the_day.py --keywords LLM agent -o json -f llm-repos.json
```

**CSV fields (repos):** `rank`, `category`, `full_name`, `stars`, `star_delta`, `daily_velocity`, `forks`, `language`, `description`, `created_at`, `updated_at`, `url`

**CSV fields (developers):** `rank`, `login`, `name`, `company`, `location`, `public_repos`, `followers`, `following`, `url`

---

## AI Relevance Filter

Post-filter results through an LLM that reads each repo's description and README snippet, then decides if it matches your intent.

```bash
# Filter results using OpenAI
python github_repo_of_the_day.py --keywords LLM --ai-filter "production-ready LLM inference servers"

# With graceful fallback when LLM is unavailable
python github_repo_of_the_day.py --keywords agent --ai-filter "autonomous coding agents" --ai-filter-fallback passthrough
```

### Supported backends

**OpenAI-compatible** (OpenAI, Ollama, LM Studio, Groq, Together AI, OpenRouter, vLLM):

```env
AI_PROVIDER=openai          # default
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-...
```

**Local Ollama example:**

```env
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama
```

**Anthropic (native Claude API):**

```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5
```

### Fallback policy

| `--ai-filter-fallback` | Behaviour when LLM is unavailable |
|---|---|
| `fail` _(default)_ | Exit with error |
| `passthrough` | Warn and return all results unfiltered |

---

## Token Setup

```bash
cp .env.example .env
# Set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx inside .env
```

| Auth state | Rate limit |
|---|---|
| No token | 60 req/hr |
| With token | 5,000 req/hr |

Get a token → [github.com/settings/tokens](https://github.com/settings/tokens)

A token can also be passed inline (overrides `.env`):

```bash
python github_repo_of_the_day.py -t ghp_xxxxxxxxxxxxxxxx
```

---

## How Search Modes Work

| Mode | Triggered by | Categories | New repos threshold | Active repos threshold |
|---|---|---|---|---|
| Browse | no keyword flags | New Today · Active Giants | stars > 10 | stars > 1,000 |
| Search | any keyword flag | New & Relevant · Active & Relevant | stars > 50 | stars > 500 |

---

## All Options

```
usage: daily-github-pulse [-h]
                          [--developers]
                          [-l LANG] [--language LANG]
                          [-p PERIOD] [--period PERIOD]
                          [-d N] [--days N]
                          [-n N] [--top N]
                          [-t TOKEN] [--token TOKEN]
                          [-k WORD] [--keyword WORD]
                          [--keywords WORD [WORD ...]]
                          [--bool-query EXPR]
                          [--keyword-op OP]
                          [--keyword-not WORD [WORD ...]]
                          [-s SCOPE] [--search-in SCOPE]
                          [--wildcard]
                          [-o FORMAT] [--output FORMAT]
                          [-f FILE] [--output-file FILE]
                          [--no-snapshot]
                          [--clear-snapshots]
                          [--ai-filter QUERY]
                          [--ai-filter-fallback POLICY]
                          [--version]

mode:
  --developers, --devs  Show trending developers instead of repositories

filters:
  -l, --language LANG   Filter by programming language (e.g. python, go, rust)
  -p, --period PERIOD   Named look-back window: day (1d), week (7d), month (30d)
                        Takes precedence over --days
  -d, --days N          Look back N days (default: 1)
  -n, --top N           Results per category (default: 10)

authentication:
  -t, --token TOKEN     GitHub personal access token — overrides .env

keyword search (mutually exclusive):
  -k, --keyword WORD    Single keyword or quoted phrase (legacy)
  --keywords WORD ...   Multiple keywords joined with --keyword-op
  --bool-query EXPR     Full boolean expression: '(A OR B) AND C AND NOT D'

keyword modifiers:
  --keyword-op OP       Connector for --keywords: AND (default) or OR
  --keyword-not WORD .. Terms to exclude (NOT clauses)
  -s, --search-in SCOPE Comma-separated search scope
                        Valid: name, description, readme
                        Default: name,description
  --wildcard            Expand ? and * in --keywords via NLTK corpus
                        Requires: pip install nltk

output:
  -o, --output FORMAT   Output format: text (default), json, csv
  -f, --output-file FILE Write output to file instead of stdout

snapshots:
  --no-snapshot         Disable snapshot load/save for this run
  --clear-snapshots     Delete all stored snapshots and exit

ai filter:
  --ai-filter QUERY     Natural-language intent for LLM relevance filter
  --ai-filter-fallback  fail (default) or passthrough

meta:
  --version             Show version and exit
  -h, --help            Show this help message and exit
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All 136 tests run without network access (GitHub API calls are fully mocked).

---

## License

[MIT](LICENSE)
