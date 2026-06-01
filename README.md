# daily-github-pulse

> Discover GitHub's top repositories of the day — with real star velocity.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Overview

`daily-github-pulse` uses the **GitHub Search API** (no scraping, no unofficial endpoints) to surface the most exciting repositories right now. It runs two complementary queries in parallel:

| Strategy | Query logic | Best for |
|---|---|---|
| 🌱 **New Today** | `created:>=<date> stars:>10` | Fresh projects gaining early traction |
| 🔥 **Active Giants** | `pushed:>=<date> stars:>1000` | Established projects with recent activity |

Repos that appear in both result sets are **deduplicated** — shown only once.

On every run, star counts are saved locally. The **next** run shows the delta (`+142 ⭐ since last run`), giving you real velocity data without any external service.

---

## Requirements

- Python 3.9+
- `requests`
- `python-dotenv` *(optional — for loading `GITHUB_TOKEN` from a `.env` file)*

```bash
pip install -r requirements.txt
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse

# Install dependencies
pip install -r requirements.txt

# Run
python github_repo_of_the_day.py
```

---

## Usage

```
python github_repo_of_the_day.py [OPTIONS]
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--period` | `-p` | — | Named look-back window: `day` (1), `week` (7), `month` (30). Takes precedence over `--days`. |
| `--days` | `-d` | `1` | Look back N days. Ignored when `--period` is used. |
| `--language` | `-l` | all | Filter by programming language (e.g. `python`, `rust`). |
| `--top` | `-n` | `10` | Repos per category (max 100). |
| `--keyword` | `-k` | — | Keyword to match against repo metadata. |
| `--search-in` | `-s` | `name,description` | Where to search the keyword: `name`, `description`, `readme`. |
| `--output` | `-o` | `text` | Output format: `text`, `json`, `csv`. |
| `--output-file` | `-f` | stdout | Write JSON/CSV to this file instead of stdout. |
| `--token` | `-t` | — | GitHub PAT — overrides `.env`. |
| `--no-snapshot` | — | off | Disable snapshot save/load for this run. |
| `--clear-snapshots` | — | — | Delete all stored snapshots and exit. |
| `--version` | — | — | Print version and exit. |

---

## Examples

```bash
# Today's top repos (default)
python github_repo_of_the_day.py

# This week's trending repos
python github_repo_of_the_day.py --period week

# This month's top Rust repos
python github_repo_of_the_day.py --period month --language rust

# Custom window: last 14 days
python github_repo_of_the_day.py --days 14

# Export as JSON to stdout, pipe into jq
python github_repo_of_the_day.py --output json | jq '.[].full_name'

# Export weekly CSV to a file
python github_repo_of_the_day.py --period week --output csv --output-file weekly.csv

# Search by keyword
python github_repo_of_the_day.py --keyword "LLM agent" --output json

# Search in README too (slower)
python github_repo_of_the_day.py --keyword "MCP server" --search-in name,description,readme

# Skip velocity tracking for a one-off run
python github_repo_of_the_day.py --no-snapshot

# Reset stored snapshots
python github_repo_of_the_day.py --clear-snapshots
```

---

## GitHub Token

Without a token, the GitHub API allows **60 requests/hour**. With a free Personal Access Token (PAT), this rises to **5,000 requests/hour**.

### Setup

1. Go to <https://github.com/settings/tokens>
2. Generate a new token (classic) — no scopes needed for public repos
3. Create a `.env` file in the project root:

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

> ⚠️ **Security**: `.env` is listed in `.gitignore`. Never commit your token.

Alternatively, pass it inline:

```bash
python github_repo_of_the_day.py --token ghp_xxxxxxxxxxxxxxxx
```

---

## Star Velocity

On each run, star counts are saved to `~/.daily-github-pulse/snapshots.json`. On the next run, the delta is shown:

```
  Δ +142 ⭐ since last run
```

On the first run, velocity shows:

```
  Δ  — (first run — no velocity data yet)
```

To reset the baseline:

```bash
python github_repo_of_the_day.py --clear-snapshots
```

---

## Sample Output

```
######################################################################
  daily-github-pulse v1.4.0  —  2026-06-01
  Auth     : Authenticated
  Velocity : enabled
######################################################################

──────────────────────────────────────────────────────────────────────
  New Today
──────────────────────────────────────────────────────────────────────
======================================================================
#1  awesome-org/cool-new-project
    Stars: 1,204  Forks: 87  Lang: Python
  Δ +342 ⭐ since last run
    Created: 2026-06-01  |  Updated: 2026-06-01
    A blazing-fast tool for doing cool things with data
    https://github.com/awesome-org/cool-new-project
```

---

## How It Works

```
CLI args
   │
   ├─ --period  ──► resolve_period() ──► effective days
   └─ --days    ──┘
         │
         ▼
  search_trending_repos()
   ├─ Query 1: New Today      (GitHub Search API)
   └─ Query 2: Active Giants  (GitHub Search API)
         │
         ▼
  Deduplication (seen_ids set)
         │
         ├─── text  ──► format_repo()      ──► stdout
         ├─── json  ──► export_json()      ──► stdout / file
         └─── csv   ──► export_csv()       ──► stdout / file
         │
         ▼
  save_snapshots()  ──►  ~/.daily-github-pulse/snapshots.json
```

**Why two strategies?** GitHub has no official `/trending` endpoint. The two-query approach captures both fresh projects gaining momentum and established projects with recent activity — together they approximate what a trending page would show.

**Why `--period` over `--days`?** For scripting and automation, named periods (`day`, `week`, `month`) are more readable and less error-prone than remembering that `--days 7` means a week. Both flags are kept for backward compatibility.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

All tests mock the GitHub API — no network access or token required.

---

## Limitations

- GitHub has no official trending endpoint. Results are a best-effort approximation via the Search API.
- Star velocity measures change between *your runs*, not absolute daily gains.
- Unauthenticated requests are limited to 60/hour; use a token for sustained use.
- `--search-in readme` is significantly slower (GitHub indexes readme content separately).

---

## Roadmap Ideas

- [ ] `--format table` — tabular terminal output using `rich`
- [ ] GitHub Actions workflow for daily digest
- [ ] Multi-day velocity tracking (7-day moving average)
- [ ] Webhook / Slack notification integration

---

## License

[MIT](LICENSE)
