# 🏆 daily-github-pulse

> Discover GitHub's top trending repositories of the day, filtered by language, recency, and star activity.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub API](https://img.shields.io/badge/GitHub-REST%20API%20v3-black?logo=github)](https://docs.github.com/en/rest)

---

## 📌 Overview

`daily-github-pulse` is a lightweight CLI tool that queries the GitHub REST API to surface the most relevant repositories of the day. Since GitHub's official API does not expose a native trending endpoint, this tool uses two complementary strategies to approximate daily trending activity:

| Strategy | Query Logic | Purpose |
|----------|-------------|--------|
| 🌱 **New Today** | `created:>=today stars:>10` | Newly created repos gaining traction fast |
| 🔥 **Active Giants** | `pushed:>=today stars:>1000` | Established repos actively updated today |

---

## ⚙️ Requirements

- Python **3.9+**
- [`requests`](https://pypi.org/project/requests/) library
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) *(optional, for token management)*

```bash
pip install requests python-dotenv
```

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse

# Install dependencies
pip install requests python-dotenv

# Run with defaults (today, all languages, top 10)
python github_repo_of_the_day.py
```

---

## 🛠️ Usage

```
python github_repo_of_the_day.py [OPTIONS]
```

### Options

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--language` | `-l` | `str` | `None` | Filter by programming language (e.g. `python`, `go`, `rust`) |
| `--days` | `-d` | `int` | `1` | Look back N days (1 = today only) |
| `--top` | `-n` | `int` | `10` | Number of repositories to display per category |
| `--token` | `-t` | `str` | `None` | GitHub Personal Access Token (overrides `.env`) |

### Examples

```bash
# Top Python repos created or active today
python github_repo_of_the_day.py --language python

# Top 5 Rust repos from the last 7 days
python github_repo_of_the_day.py --language rust --days 7 --top 5

# All languages, top 20, last 3 days
python github_repo_of_the_day.py --days 3 --top 20
```

---

## 🔑 GitHub Token (Highly Recommended)

Without authentication, the GitHub API allows only **60 requests/hour**. With a Personal Access Token (PAT), this increases to **5,000 requests/hour**.

### How to get a token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Select scope: `public_repo` (read-only access is enough)
4. Copy the generated token

### Storing your token safely with `.env`

Create a `.env` file in the project root:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
```

The script automatically loads it via `python-dotenv`. **No extra flags needed.**

> ⚠️ **Always add `.env` to your `.gitignore`** to prevent accidental commits:
> ```
> echo ".env" >> .gitignore
> ```

The `--token` CLI flag is still available if you need to override the `.env` value temporarily.

---

## 📋 Sample Output

```
######################################################################
  GitHub Repo of the Day - 2026-06-01
  Authenticated
######################################################################

──────────────────────────────────────────────────────────────────────
  New Today
──────────────────────────────────────────────────────────────────────
======================================================================
#1  awesome-dev/blazing-fast-orm
    Stars: 1,243  Forks: 87  Lang: Rust
    Created: 2026-06-01  |  Updated: 2026-06-01
    A zero-overhead ORM for Rust with async-first design
    https://github.com/awesome-dev/blazing-fast-orm
```

---

## 🏗️ Project Structure

```
daily-github-pulse/
├── github_repo_of_the_day.py   # Main CLI script
├── .env                        # Your GitHub token (never commit this)
├── .env.example                # Safe template to share with others
├── .gitignore                  # Excludes .env and cache files
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── CHANGELOG.md                # Version history
├── CONTRIBUTING.md             # Contribution guidelines
├── LICENSE                     # MIT License
└── .github/
    └── ISSUE_TEMPLATE/
        ├── bug_report.md       # Bug report template
        └── feature_request.md  # Feature request template
```

---

## 📐 How It Works

```
┌─────────────────────────────────────────────────────┐
│                   CLI Arguments                     │
│   --language  --days  --top  --token                │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│             search_trending_repos()                 │
│                                                     │
│  Query 1: created:>=DATE stars:>10 [language]       │
│  Query 2: pushed:>=DATE stars:>1000 [language]      │
└──────────────────┬──────────────────┬───────────────┘
                   │                  │
                   ▼                  ▼
         New Today              Active Giants
         (sorted by stars)      (sorted by stars)
                   │                  │
                   └────────┬─────────┘
                            ▼
                   format_repo() + print
```

### Why two strategies?

The GitHub Search API sorts by **total stars**, not **stars gained today**. A newly created viral repo won't appear if filtered only by total stars. Conversely, a well-known project updated today won't show up in a `created:today` filter. Using both strategies together gives a more complete picture of what's hot right now.

---

## ⚠️ Limitations

- GitHub API has **no official trending endpoint** — this tool approximates trending activity
- **Star velocity** (stars gained per day) is not available via the public API without scraping
- Rate limits apply: 60 req/hr unauthenticated, 5,000 req/hr with a token
- Results reflect **total stars**, not daily gain

---

## 🔮 Roadmap Ideas

- [ ] Add `--output json` flag to export results as JSON
- [ ] Cache results locally to avoid repeated API calls
- [ ] Add star delta estimation by comparing snapshots over time
- [ ] Daily digest email/Telegram bot integration
- [ ] GitHub Actions workflow for scheduled daily runs

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT © [Ali Aghili](https://zil.ink/thedatascientist)

---

## 🙏 Acknowledgments

Built on top of the [GitHub REST API v3](https://docs.github.com/en/rest/search/search#search-repositories).
