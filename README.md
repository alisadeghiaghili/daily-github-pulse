# 🏆 daily-github-pulse

> Discover GitHub's top trending repositories of the day — with real **star velocity**.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub API](https://img.shields.io/badge/GitHub-REST%20API%20v3-black?logo=github)](https://docs.github.com/en/rest)
[![Version](https://img.shields.io/badge/version-1.2.0-informational)](CHANGELOG.md)

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
| `--search-in` | `-s` | `name,description` | Where to search the keyword: `name`, `description`, `readme` |
| `--no-snapshot` | | `False` | Skip velocity tracking for this run |
| `--clear-snapshots` | | — | Delete all stored snapshots and exit |
| `--version` | | — | Print version and exit |

### Examples

```bash
# Today's top repos, all languages
python github_repo_of_the_day.py

# Filter by language
python github_repo_of_the_day.py --language python

# Search by keyword in name + description
python github_repo_of_the_day.py --keyword "LLM agent"

# Search in README too (slower)
python github_repo_of_the_day.py --keyword "vector database" --search-in name,description,readme

# Top 5 Rust repos from the last 7 days
python github_repo_of_the_day.py --language rust --days 7 --top 5

# Run without saving/loading snapshots
python github_repo_of_the_day.py --no-snapshot

# Reset all stored velocity data
python github_repo_of_the_day.py --clear-snapshots
```

---

## ⭐ Star Velocity

GitHub's public API exposes **total star counts only** — not how many stars a repo gained today. `daily-github-pulse` solves this with a simple local snapshot mechanism:

```
First run                    Second run (next day)
────────────────────         ────────────────────────────────
Repo X  →  12,400 ⭐  →  saved   Repo X  →  12,542 ⭐
                                 delta = 12,542 − 12,400 = +142 ⭐
```

Snapshots are stored in `~/.daily-github-pulse/snapshots.json`. The delta is shown inline for each repo:

```
#1  trending-dev/awesome-tool
    Stars: 12,542  Forks: 834  Lang: Python
    Δ +142 ⭐ since last run
    Created: 2025-03-10  |  Updated: 2026-06-01
    ...
```

On the **first run**, no delta is available yet — it will show:
```
    Δ  — (first run — no velocity data yet)
```

### Snapshot management

```bash
# Skip snapshot for a single run (e.g. in CI or testing)
python github_repo_of_the_day.py --no-snapshot

# Clear all stored data
python github_repo_of_the_day.py --clear-snapshots
```

---

## 🔍 Keyword Search

Use `--keyword` to filter results by a topic or term:

```bash
# Matches repos where name or description contains the keyword
python github_repo_of_the_day.py --keyword "self-hosted"

# Also search inside README files (significantly slower)
python github_repo_of_the_day.py --keyword "MCP server" --search-in name,description,readme
```

> ⚠️ `readme` search triggers GitHub's full-text index and can take 10–15 seconds.
> Use it only when name/description search is too narrow.

---

## 🔑 GitHub Token (Highly Recommended)

Without authentication the GitHub API allows only **60 requests/hour**.
With a Personal Access Token (PAT) this increases to **5,000 requests/hour**.

### Setup

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Select scope: `public_repo` (read-only is enough)
4. Create a `.env` file in the project root:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

> ⚠️ Always add `.env` to `.gitignore` before committing:
> ```bash
> echo ".env" >> .gitignore
> ```

The `--token` flag overrides `.env` for a single run.

---

## 📋 Sample Output

```
######################################################################
  daily-github-pulse v1.2.0  —  2026-06-01
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
├── github_repo_of_the_day.py   # Main CLI script
├── .env                        # Your GitHub token (never commit this)
├── .env.example                # Safe template to share
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
┌────────────────────────────────────────────────────────┐
│                     CLI Arguments                      │
│  --language  --days  --top  --keyword  --search-in     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
               load_snapshots()  ◄── ~/.daily-github-pulse/snapshots.json
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│              search_trending_repos()                   │
│                                                        │
│  Query 1: created:>=DATE stars:>10  [keyword] [lang]   │
│  Query 2: pushed:>=DATE stars:>1000 [keyword] [lang]   │
│                                                        │
│  Deduplication: repos in both queries → shown once     │
└──────────────┬─────────────────────┬───────────────────┘
               │                     │
               ▼                     ▼
         New Today             Active Giants
               │                     │
               └──────────┬──────────┘
                          ▼
              star_delta(repo, snapshots)
                          │
                          ▼
              format_repo() + print
                          │
                          ▼
               save_snapshots()  ──► ~/.daily-github-pulse/snapshots.json
```

---

## ⚠️ Limitations

- GitHub API has **no official trending endpoint** — activity is approximated
- **Velocity accuracy** depends on how frequently you run the tool; a bigger gap between runs means a larger (less granular) delta
- Rate limits: 60 req/hr unauthenticated · 5,000 req/hr authenticated
- `readme` search is significantly slower due to full-text indexing

---

## 🔮 Roadmap

- [ ] `--output json/csv` — export results for downstream automation
- [ ] `--period day/week/month` — standardised time window flags
- [ ] GitHub Actions workflow — scheduled daily runs with Telegram/Slack notify
- [ ] PyPI package — `pip install daily-github-pulse`
- [ ] Topic/category filter — e.g. `--topic ai`, `--topic devops`
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
