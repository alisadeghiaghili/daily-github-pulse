# 🏆 daily-github-pulse

> Discover GitHub's top trending repositories of the day — with real **star velocity**.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub API](https://img.shields.io/badge/GitHub-REST%20API%20v3-black?logo=github)](https://docs.github.com/en/rest)
[![Version](https://img.shields.io/badge/version-1.3.0-informational)](CHANGELOG.md)

---

## 📌 Overview

`daily-github-pulse` is a lightweight CLI tool that queries the GitHub REST API to surface the most relevant repositories of the day. Since GitHub's official API does not expose a native trending endpoint, this tool uses two complementary strategies — and tracks **star velocity** locally so you can see how fast a repo is actually growing.

| Strategy | Query Logic | Purpose |
|----------|-------------|--------|
| 🌱 **New Today** | `created:>=today stars:>10` | Newly created repos gaining traction fast |
| 🔥 **Active Giants** | `pushed:>=today stars:>1000` | Established repos actively updated today |

---

## ⚙️ Requirements

- Python **3.9+**
- [`requests`](https://pypi.org/project/requests/)
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) *(optional — for `.env` token management)*

```bash
pip install requests python-dotenv
```

---

## 🚀 Quick Start

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install requests python-dotenv
python github_repo_of_the_day.py
```

---

## 🛠️ Usage

```
python github_repo_of_the_day.py [OPTIONS]
```

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--language` | `-l` | `None` | Filter by programming language (e.g. `python`, `go`, `rust`) |
| `--days` | `-d` | `1` | Look back N days (1 = today only) |
| `--top` | `-n` | `10` | Repos per category |
| `--token` | `-t` | `None` | GitHub PAT — overrides `.env` |
| `--keyword` | `-k` | `None` | Keyword to search in repo metadata |
| `--search-in` | `-s` | `name,description` | Where to search: `name`, `description`, `readme` |
| `--output` | `-o` | `text` | Output format: `text`, `json`, `csv` |
| `--output-file` | `-f` | `None` | Write JSON/CSV to file instead of stdout |
| `--no-snapshot` | | `False` | Skip velocity tracking for this run |
| `--clear-snapshots` | | — | Delete all stored snapshots and exit |
| `--version` | | — | Print version and exit |

### Examples

```bash
# Today's top repos, default text output
python github_repo_of_the_day.py

# Export as JSON to stdout (pipe-friendly)
python github_repo_of_the_day.py --output json

# Export JSON and pipe into jq
python github_repo_of_the_day.py --output json | jq '.[].full_name'

# Save CSV to file
python github_repo_of_the_day.py --output csv --output-file results.csv

# Python repos, CSV export
python github_repo_of_the_day.py --language python --output csv --output-file python_today.csv

# Keyword + JSON export
python github_repo_of_the_day.py --keyword "LLM agent" --output json

# Top 5 Rust repos from the last 7 days
python github_repo_of_the_day.py --language rust --days 7 --top 5
```

---

## 📤 Export Formats

### JSON

Outputs a flat JSON array. Each element corresponds to one repo:

```json
[
  {
    "rank": 1,
    "category": "New Today",
    "full_name": "owner/repo",
    "stars": 12542,
    "star_delta": 142,
    "forks": 834,
    "language": "Python",
    "description": "A blazing fast toolkit",
    "created_at": "2025-03-10",
    "updated_at": "2026-06-01",
    "url": "https://github.com/owner/repo"
  }
]
```

`star_delta` is `null` on the first run (no previous snapshot to compare against).

### CSV

Same fields as JSON, one row per repo. Encoded as **UTF-8 with BOM** so it opens
correctly in Excel and LibreOffice without manual encoding selection.

```
rank,category,full_name,stars,star_delta,forks,language,description,created_at,updated_at,url
1,New Today,owner/repo,12542,142,834,Python,A blazing fast toolkit,2025-03-10,2026-06-01,https://...
```

### Piping and automation

```bash
# Feed into jq
python github_repo_of_the_day.py --output json | jq '[.[] | {name: .full_name, velocity: .star_delta}]'

# Daily cron job — save timestamped CSV
python github_repo_of_the_day.py --output csv --output-file "pulse_$(date +%F).csv"

# GitHub Actions step
- run: python github_repo_of_the_day.py --output json --output-file pulse.json
```

> ℹ️ When writing to a file (`--output-file`), the confirmation line is printed
> to **stderr** so it never contaminates piped output.

---

## ⭐ Star Velocity

GitHub's public API exposes **total star counts only** — not daily gain.
`daily-github-pulse` tracks this locally:

```
First run                    Second run (next day)
────────────────────         ────────────────────────────────
Repo X  →  12,400 ⭐  →  saved   Repo X  →  12,542 ⭐
                                 delta = 12,542 − 12,400 = +142 ⭐
```

Snapshots: `~/.daily-github-pulse/snapshots.json`

```bash
python github_repo_of_the_day.py --no-snapshot      # skip this run
python github_repo_of_the_day.py --clear-snapshots  # reset all data
```

---

## 🔍 Keyword Search

```bash
# Matches repos where name or description contains the keyword
python github_repo_of_the_day.py --keyword "self-hosted"

# Also search inside README (significantly slower)
python github_repo_of_the_day.py --keyword "MCP server" --search-in name,description,readme
```

> ⚠️ `readme` search can take 10–15 seconds. Use it only when name/description is too narrow.

---

## 🔑 GitHub Token (Highly Recommended)

Without a token: **60 req/hr**. With a PAT: **5,000 req/hr**.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Generate new token (classic), scope: `public_repo`
3. Create `.env` in project root:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

> ⚠️ Always add `.env` to `.gitignore`.

---

## 📋 Sample Output

```
######################################################################
  daily-github-pulse v1.3.0  —  2026-06-01
  Language : python
  Auth     : Authenticated
  Velocity : enabled
######################################################################

──────────────────────────────────────────────────────────────────────
  New Today
──────────────────────────────────────────────────────────────────────
======================================================================
#1  trending-dev/awesome-tool
    Stars: 12,542  Forks: 834  Lang: Python
    Δ +142 ⭐ since last run
    Created: 2025-03-10  |  Updated: 2026-06-01
    A blazing fast Python toolkit for async data pipelines
    https://github.com/trending-dev/awesome-tool

  Snapshot saved → /home/ali/.daily-github-pulse/snapshots.json
```

---

## 🏗️ Project Structure

```
daily-github-pulse/
├── github_repo_of_the_day.py
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
└── .github/
    └── ISSUE_TEMPLATE/
```

---

## 📐 How It Works

```
CLI args
   │
   ▼
load_snapshots()  ◄── ~/.daily-github-pulse/snapshots.json
   │
   ▼
search_trending_repos()
   ├── New Today
   └── Active Giants
        │   (deduplication across categories)
        ▼
   output_fmt == "text"  →  format_repo() + print
   output_fmt == "json"  →  build_export_row() → export_json() → write_output()
   output_fmt == "csv"   →  build_export_row() → export_csv()  → write_output()
        │
        ▼
save_snapshots()  ──► ~/.daily-github-pulse/snapshots.json
```

---

## ⚠️ Limitations

- GitHub API has **no official trending endpoint** — activity is approximated
- Velocity accuracy depends on run frequency; larger gaps mean coarser deltas
- Rate limits: 60 req/hr unauthenticated · 5,000 req/hr authenticated
- `readme` search is significantly slower (full-text index)

---

## 🔮 Roadmap

- [x] Star velocity via local snapshots
- [x] `--output json/csv` export
- [ ] `--period day/week/month` standardised time windows
- [ ] GitHub Actions workflow + Telegram/Slack notify
- [ ] PyPI package — `pip install daily-github-pulse`
- [ ] Topic/category filter (`--topic ai`, `--topic devops`)
- [ ] Trending developers (not just repos)

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📄 License

MIT © [Ali Aghili](https://zil.ink/thedatascientist)

---

## 🙏 Acknowledgments

Built on the [GitHub REST API v3](https://docs.github.com/en/rest/search/search#search-repositories).
