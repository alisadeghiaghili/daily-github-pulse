# daily-github-pulse

> Discover GitHub's top trending repositories and developers of the day — with real star velocity, boolean keyword search, and wildcard expansion.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Features

| Feature | Flag | Notes |
|---|---|---|
| Browse trending repos | _(default)_ | New Today + Active Giants |
| Trending developers | `--developers` | Rising Stars + Active Veterans |
| Language filter | `--language python` | Any GitHub language slug |
| Look-back period | `--period week` | `day` / `week` / `month` or `--days N` |
| Single keyword | `--keyword "LLM agent"` | Searches name + description |
| Multi-keyword boolean | `--keywords LLM agent` | AND / OR via `--keyword-op` |
| Full boolean expression | `--bool-query '(LLM OR GPT) AND agent'` | Supports NOT and parentheses |
| Exclusion terms | `--keyword-not benchmark survey` | Appends `NOT "term"` clauses |
| **Wildcard expansion** | `--wildcard` | `analy?e` → `analyse OR analyze` |
| Search scope | `--search-in name,description,readme` | readme is slower |
| Star velocity | _(auto)_ | Stars/day, time-normalised |
| Export formats | `--output json/csv` | Pipe-friendly |
| File export | `--output-file results.csv` | json or csv |

---

## Installation

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt

# Optional: wildcard expansion support
pip install nltk

# Recommended: add your GitHub token (raises rate limit to 5,000 req/hr)
cp .env.example .env
# edit .env and set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

---

## Quick Start

```bash
# Today's top repos (all languages)
python github_repo_of_the_day.py

# Top Python repos this week
python github_repo_of_the_day.py --language python --period week

# Search for LLM + agent repos
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# Full boolean query
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'

# Wildcard: analy?e → analyse OR analyze
python github_repo_of_the_day.py --keywords "analy?e" --wildcard

# Trending developers
python github_repo_of_the_day.py --developers --language python
```

---

## Keyword Search

### Single keyword (legacy)
```bash
python github_repo_of_the_day.py --keyword "vector database"
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
```

Supported syntax: `AND`, `OR`, `NOT`, quoted phrases `"multi word"`, and parentheses `(A OR B) AND C`.

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

> **Without `nltk`:** `--wildcard` is a no-op — terms pass through unchanged. No crash, no warning.

---

## Star Velocity

On each run, star counts are saved to `~/.daily-github-pulse/snapshots.json`.
On subsequent runs, two numbers are shown:

- **Δ raw** — total stars gained since last snapshot
- **~N ⭐/day** — time-normalised rate (stays meaningful across long gaps)

```
  Δ +1,400 ⭐ total  |  ~200.0 ⭐/day
```

```bash
# Skip snapshot for this run
python github_repo_of_the_day.py --no-snapshot

# Reset all snapshots
python github_repo_of_the_day.py --clear-snapshots
```

---

## Export

```bash
# JSON to stdout (pipe into jq)
python github_repo_of_the_day.py --output json | jq '.[].full_name'

# CSV to file
python github_repo_of_the_day.py --output csv --output-file results.csv

# Developers as JSON
python github_repo_of_the_day.py --developers --output json
```

---

## All Options

```
usage: daily-github-pulse [-h] [--developers] [--language LANG]
                          [--period PERIOD] [--days N] [--top N]
                          [--token TOKEN] [--keyword WORD]
                          [--keywords WORD [WORD ...]]
                          [--bool-query EXPR]
                          [--keyword-op OP]
                          [--keyword-not WORD [WORD ...]]
                          [--search-in SCOPE]
                          [--wildcard]
                          [--output FORMAT] [--output-file FILE]
                          [--no-snapshot] [--clear-snapshots] [--version]

options:
  --developers          Show trending developers instead of repositories
  --language LANG       Filter by language (e.g. python, go, rust)
  --period PERIOD       day / week / month  (overrides --days)
  --days N              Look back N days (default: 1)
  --top N               Results per category (default: 10)
  --token TOKEN         GitHub PAT — overrides .env
  --keyword WORD        Single keyword search (legacy)
  --keywords WORD ...   Multi-keyword boolean search
  --bool-query EXPR     Full boolean expression: '(A OR B) AND C AND NOT D'
  --keyword-op OP       AND (default) or OR connector for --keywords
  --keyword-not WORD .. Exclude terms via NOT clauses
  --search-in SCOPE     name,description,readme  (default: name,description)
  --wildcard            Expand ? and * in --keywords via NLTK corpus
  --output FORMAT       text (default), json, csv
  --output-file FILE    Write output to file (json/csv)
  --no-snapshot         Skip snapshot I/O for this run
  --clear-snapshots     Delete snapshot file and exit
  --version             Show version and exit
```

---

## Token Setup

```bash
cp .env.example .env
# Set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx inside .env
```

Without a token: 60 req/hr (unauthenticated).  
With a token: 5,000 req/hr.

Get a token → [github.com/settings/tokens](https://github.com/settings/tokens)

---

## How Search Modes Work

| Mode | Triggered by | New repos threshold | Active repos threshold |
|---|---|---|---|
| Browse | no keyword flags | stars > 10 | stars > 1,000 |
| Search | any keyword flag | stars > 50 | stars > 500 |

---

## License

[MIT](LICENSE)
