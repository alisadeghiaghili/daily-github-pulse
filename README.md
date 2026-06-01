# daily-github-pulse

> Discover GitHub's top repositories of the day — with real star velocity.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![Tests](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Overview

`daily-github-pulse` uses the **GitHub Search API** (no scraping, no unofficial endpoints) to surface the most exciting repositories right now. It runs two complementary queries in parallel:

| Strategy | Query logic | Best for |
|---|---|---|
| 🌱 **New Today** | `created:>=<date> stars:>10` | Fresh projects gaining early traction |
| 🔥 **Active Giants** | `pushed:>=<date> stars:>1000` | Established projects with recent activity |

Repos that appear in both result sets are **deduplicated** — shown only once.

---

## Star Velocity

On each run, star counts **and a UTC timestamp** are saved locally. The next run computes two numbers:

| Metric | Formula | What it tells you |
|---|---|---|
| `star_delta` | `current − snapshot` | Total stars gained since last run |
| `daily_velocity` | `star_delta ÷ elapsed_days` | Stars per day — stays meaningful even after a long gap |

```
  Δ +700 ⭐ total  |  ~100.0 ⭐/day
```

If you run the tool daily the two numbers are similar. If you haven't run it for two weeks, `star_delta` might be large but `daily_velocity` will still show the true per-day rate — the number that actually lets you compare repos fairly.

On the first run (no previous snapshot):

```
  Δ  — (first run — no velocity data yet)
```

To reset the baseline:

```bash
python github_repo_of_the_day.py --clear-snapshots
```

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
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt
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
python github_repo_of_the_day.py --output json | jq '.[].daily_velocity'

# Export weekly CSV to a file
python github_repo_of_the_day.py --period week --output csv --output-file weekly.csv

# Search by keyword
python github_repo_of_the_day.py --keyword "LLM agent" --output json

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

---

## Sample Output

```
######################################################################
  daily-github-pulse v1.5.0  —  2026-06-01
  Auth     : Authenticated
  Velocity : enabled
######################################################################

──────────────────────────────────────────────────────────────────────
  New Today
──────────────────────────────────────────────────────────────────────
======================================================================
#1  awesome-org/cool-new-project
    Stars: 1,204  Forks: 87  Lang: Python
  Δ +342 ⭐ total  |  ~171.0 ⭐/day
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
  load_snapshots()  ◄──  ~/.daily-github-pulse/snapshots.json
         │
         ▼
  For each repo:
   ├─ star_delta()      = current_stars − snapshot_stars
   ├─ elapsed_days()    = (now − saved_at).total_seconds / 86400
   └─ daily_velocity()  = star_delta / elapsed_days  [⭐/day]
         │
         ├─── text  ──► format_repo()   ──► stdout
         ├─── json  ──► export_json()   ──► stdout / file
         └─── csv   ──► export_csv()    ──► stdout / file
         │
         ▼
  save_snapshots()  ──►  ~/.daily-github-pulse/snapshots.json
                         (stars + UTC timestamp per repo)
```

---

## CI / Continuous Integration

Every push and pull request to `main` automatically runs the full test suite across **Python 3.9 – 3.14** via GitHub Actions.

### Telegram Notifications (optional)

Add two secrets to **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ID of the chat/channel to notify |

If the secrets are not set, the notify step is skipped silently.

---

## Running Tests Locally

```bash
pip install pytest
pytest tests/ -v
```

All tests mock the GitHub API — no network access or token required.

---

## Limitations

- GitHub has no official trending endpoint. Results are a best-effort approximation via the Search API.
- `daily_velocity` measures growth between *your runs*, not GitHub's internal counters.
- Unauthenticated requests are limited to 60/hour; use a token for sustained use.
- `--search-in readme` is significantly slower.

---

## Roadmap Ideas

- [ ] `--format table` — tabular terminal output using `rich`
- [ ] Scheduled GitHub Actions for daily digest
- [ ] Multi-day velocity moving average (7-day)
- [ ] Slack / webhook notification integration

---

## License

[MIT](LICENSE)
