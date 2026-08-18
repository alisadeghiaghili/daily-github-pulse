# daily-github-pulse

> Find out what's blowing up on GitHub — every single day.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Tests](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

[فارسی](README.md) | [Deutsch](README.de.md)

---

Find out what's blowing up across **GitHub, GitLab, Gitea/Codeberg, and Bitbucket** — every single day.

`daily-github-pulse` turns trending discovery into a single command:

```bash
python daily_github_pulse.py                           # GitHub (default)
python daily_github_pulse.py --forge gitlab            # GitLab
python daily_github_pulse.py --forge gitea --gitea-url https://codeberg.org
python daily_github_pulse.py --forge github,gitlab     # Merged from both
```

You get a ranked list of repositories that gained the most stars **today**, along with a real daily growth rate — not just a total star count.

If `rich` is installed the output renders as a colour table with clickable links:

```
╭──────────────────────────────────────────────────────────────╮
│  🔍  Trending Repositories  — last 1 day                     │
╰──────────────────────────────────────────────────────────────╯

  #   Repository              ⭐ Stars    Δ Stars          Lang        Description
 ─────────────────────────────────────────────────────────────────────────────────
  1   openai/openai-python    24,312    +418 ⭐ ~418/day   Python      OpenAI Python client
  2   astral-sh/uv            18,901    +312 ⭐ ~312/day   Rust        Fast Python package manager
```

---

## Get Started in 30 Seconds

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt      # includes rich for coloured output

# Recommended: add a GitHub token (raises limit from 60 to 5,000 req/hr)
cp .env.example .env
# Set GITHUB_TOKEN=ghp_... inside .env

python github_repo_of_the_day.py
```

No complex setup. No config files. Just run it.

---

## Real-World Examples

```bash
# Top Python repos this week
python github_repo_of_the_day.py -l python -p week

# Looking for LLM + agent projects?
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'

# Wildcard: analy?e → analyse OR analyze
python github_repo_of_the_day.py --keywords "analy?e" --wildcard

# Trending developers
python github_repo_of_the_day.py --developers -l python

# Export to CSV
python github_repo_of_the_day.py -l go -o csv -f results.csv

# AI-powered filter — only production-ready inference servers
python github_repo_of_the_day.py --keywords LLM --ai-filter --ai-filter-query "production-ready LLM inference servers"
```

---

## Why This Tool?

| The Problem | The Solution |
|---|---|
| GitHub Trending only shows total star counts | **Star velocity** — actual growth rate today (`⭐/day`) |
| Search is binary — keyword matches or it doesn't | **Full boolean search**: `(LLM OR GPT) AND agent AND NOT survey` |
| Wildcard patterns require manual expansion | **Wildcard expansion** via NLTK: `analy?e` → `analyse OR analyze` |
| Results are flooded with papers and surveys | **AI filter** — describe your intent in plain English |
| Every run starts from zero | **Snapshots** — star delta since your last run |
| Plain-text output is hard to scan | **Rich UI** — colour tables, clickable links, progress bar |

---

## Rich Terminal Output (optional)

`rich` is included as a recommended dependency in `requirements.txt`. When installed:

- Rounded colour tables with per-column styles
- Clickable hyperlinks on repo and developer names
- Language colour-coding (Python → yellow, Rust → red, Go → cyan, …)
- Δ Stars in green (positive) or red (negative)
- Spinner + progress bar during the AI filter stage

Without `rich` the tool falls back to its original plain-text output automatically — no crash, no warning.

```bash
pip install rich   # one-time install
```

---

## How Star Velocity Works

On every run, star counts are saved to `~/.daily-github-pulse/snapshots.json`. The next time you run it, two numbers appear next to each repo:

- **Δ raw** — total stars gained since the last snapshot
- **~N ⭐/day** — time-normalised daily rate (stays meaningful even after a two-week gap)

```bash
# Skip saving a snapshot for this run
python github_repo_of_the_day.py --no-snapshot

# Wipe all stored snapshots
python github_repo_of_the_day.py --clear-snapshots
```

---

## Keyword Search

### Single keyword

```bash
python github_repo_of_the_day.py --keyword "vector database"
```

### Multi-keyword boolean

```bash
# AND: both terms must appear
python github_repo_of_the_day.py --keywords LLM agent --keyword-op AND

# OR: either term
python github_repo_of_the_day.py --keywords LLM GPT Claude --keyword-op OR

# Exclude terms
python github_repo_of_the_day.py --keywords LLM agent --keyword-not benchmark survey
```

### Full boolean expression

```bash
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'
```

| Syntax | Meaning | Example |
|---|---|---|
| `A AND B` | Both must appear | `LLM AND agent` |
| `A OR B` | Either must appear | `LLM OR GPT` |
| `NOT A` | Exclude term | `NOT benchmark` |
| `(A OR B) AND C` | Grouping | `(LLM OR GPT) AND agent` |
| `"multi word"` | Quoted phrase | `"large language model"` |

### Wildcard expansion

Requires `pip install nltk`.

```bash
# ? = exactly one character
python github_repo_of_the_day.py --keywords "analy?e" --wildcard
# → query becomes: (analyse OR analyze)

# * = zero or more characters
python github_repo_of_the_day.py --keywords "optimiz*" agent --wildcard
# → query becomes: (optimize OR optimized OR optimizing ...) AND agent
```

> Without `nltk`, `--wildcard` is a no-op. Terms pass through unchanged. No crash.

### Search scope

```bash
# Default: name and description only
python github_repo_of_the_day.py --keywords MCP server

# Also search README content
python github_repo_of_the_day.py --keywords MCP server -s name,description,readme
```

---

## AI Relevance Filter

Post-filter results through an LLM that reads each repo's description and README snippet, then decides whether it matches your intent.

```bash
python github_repo_of_the_day.py --keywords LLM --ai-filter --ai-filter-query "production-ready LLM inference servers"

# With graceful fallback when LLM is unavailable
python github_repo_of_the_day.py --keywords agent --ai-filter --ai-filter-query "autonomous coding agents" --ai-filter-fallback passthrough
```

### Supported Backends

**OpenAI-compatible** (OpenAI, Ollama, LM Studio, Groq, Together AI, OpenRouter, vLLM):

```env
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-...
```

**Local Ollama:**

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

| `--ai-filter-fallback` | Behaviour when LLM is unavailable |
|---|---|
| `fail` _(default)_ | Exit with error |
| `passthrough` | Warn and return all results unfiltered |

---

## GitHub Rate Limits

| Auth state | Rate limit |
|---|---|
| No token | 60 req/hr |
| With token | 5,000 req/hr |

Get a token → [github.com/settings/tokens](https://github.com/settings/tokens)

---

## All Options

<details>
<summary>Full flag reference</summary>

| Category | Flag | Description |
|---|---|---|
| Forge | `--forge NAME[,NAME...]` | Forge(s) to search: `github` (default), `gitlab`, `gitea`, `bitbucket` |
| Forge | `--gitea-url URL` | Gitea/Codeberg instance URL (default: `https://gitea.com`) |
| Mode | `--developers` | Show trending developers instead of repos |
| Filter | `-l LANG` | Programming language (e.g. `python`, `go`, `rust`) |
| Filter | `-p PERIOD` | Time window: `day` / `week` / `month` |
| Filter | `-n N` | Results per category (default: 10) |
| Search | `--keyword TERM` | Single keyword (legacy) |
| Search | `--keywords A B` | Multiple keywords with boolean operator |
| Search | `--keyword-op AND\|OR` | Connector for `--keywords` |
| Search | `--keyword-not A B` | Terms to exclude |
| Search | `--bool-query 'EXPR'` | Full boolean expression |
| Search | `--search-in SCOPE` | `name`, `description`, `readme` |
| Search | `--wildcard` | Wildcard expansion via NLTK |
| Output | `-o json\|csv` | Output format |
| Output | `-f FILE` | Write to file instead of stdout |
| Snapshot | `--no-snapshot` | Disable velocity tracking for this run |
| Snapshot | `--clear-snapshots` | Delete all stored snapshots |
| AI | `--ai-filter` | Enable LLM relevance filter |
| AI | `--ai-filter-query "QUERY"` | Natural-language description of your intent |
| AI | `--ai-filter-fallback` | `fail` or `passthrough` |

</details>

---

## Export

```bash
# JSON to stdout (pipe into jq)
python github_repo_of_the_day.py -o json | jq '.[].full_name'

# CSV to file
python github_repo_of_the_day.py -o csv -f results.csv

# Developers as JSON
python github_repo_of_the_day.py --developers -o json
```

**CSV fields (repos):** `rank`, `category`, `full_name`, `stars`, `star_delta`, `daily_velocity`, `forks`, `language`, `description`, `created_at`, `updated_at`, `url`

**CSV fields (developers):** `rank`, `login`, `name`, `company`, `location`, `public_repos`, `followers`, `following`, `url`

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

**221 tests** — no network access required (all APIs fully mocked).

| Test file | Coverage |
|---|---|
| `tests/test_github_repo.py` | All core functions, search, boolean parser, wildcard, snapshots |
| `tests/test_rich_display.py` | All `rich_display.py` public functions, rich + fallback paths |
| `tests/test_github.py` | GitHub forge client |
| `tests/test_gitlab.py` | GitLab forge client |
| `tests/test_gitea.py` | Gitea/Codeberg forge client |
| `tests/test_bitbucket.py` | Bitbucket forge client |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style, commit conventions, and the PR checklist.

---

## License

[MIT](LICENSE)
