# Contributing to daily-github-pulse

Thank you for taking the time to contribute! 🎉  
This document covers everything you need to get from zero to a merged pull request.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Running the Tests](#running-the-tests)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Commit Message Convention](#commit-message-convention)
- [Pull Request Checklist](#pull-request-checklist)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Code Style](#code-style)

---

## Code of Conduct

Be respectful and constructive. Harassment, discrimination, or disrespectful behaviour will not be tolerated.  
When in doubt, assume good intent.

---

## How Can I Contribute?

| Type | Where to start |
|---|---|
| 🐛 Bug fix | Open an issue first, or pick an existing one |
| ✨ New feature | Open a feature request issue and wait for a `help wanted` or `accepted` label before starting |
| 📝 Documentation | PRs welcome at any time — no issue needed |
| 🧪 Tests | More coverage is always appreciated |
| 🔧 Refactor | Discuss in an issue first to avoid wasted effort |

---

## Development Setup

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/<your-username>/daily-github-pulse.git
cd daily-github-pulse

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install runtime dependencies
pip install -r requirements.txt

# 4. Install dev dependencies
pip install pytest

# 5. Optional: wildcard expansion support
pip install nltk

# 6. Copy the env template and add your GitHub token
cp .env.example .env
# Edit .env and set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx

# 7. Verify everything works
python github_repo_of_the_day.py --top 3
```

---

## Running the Tests

The test suite requires no network access — all GitHub API calls are mocked.

```bash
# Run all tests
pytest tests/ -v

# Run a specific test class
pytest tests/ -v -k TestParseBooleanQuery

# Run with coverage (requires pytest-cov)
pip install pytest-cov
pytest tests/ --cov=github_repo_of_the_day --cov-report=term-missing
```

All 136 tests must pass before opening a PR. The CI matrix runs on Python 3.9–3.14.

---

## Project Structure

```
daily-github-pulse/
├── github_repo_of_the_day.py   # All source code (single-file project)
├── tests/
│   └── test_github_repo.py     # Full test suite (pytest)
├── .github/
│   └── workflows/
│       └── tests.yml           # CI workflow (runs on push + PR to main)
├── requirements.txt
├── .env.example
├── CHANGELOG.md
├── CONTRIBUTING.md
└── README.md
```

This is intentionally a **single-file project**. All logic lives in `github_repo_of_the_day.py`.  
If you think the code needs splitting into modules, open an issue for discussion first.

---

## Making Changes

```bash
# 1. Create a feature branch from main
git checkout main
git pull upstream main          # sync with the original repo
git checkout -b feat/your-feature-name

# 2. Make your changes
# ...

# 3. Run the tests
pytest tests/ -v

# 4. Quick smoke test against the real API (optional, needs token)
python github_repo_of_the_day.py --top 3

# 5. Commit
git add -p                      # stage changes selectively
git commit -m "feat: add your feature"

# 6. Push and open a PR
git push origin feat/your-feature-name
```

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<optional scope>): <short description>

[optional body — wrap at 72 chars]

[optional footer — e.g. Closes #42]
```

| Type | When to use | Example |
|---|---|---|
| `feat` | New user-facing feature | `feat: add --sort-by forks flag` |
| `fix` | Bug fix | `fix: handle empty keyword list gracefully` |
| `docs` | Documentation only | `docs: add wildcard examples to README` |
| `test` | Adding or fixing tests | `test: cover NOT inside nested parens` |
| `refactor` | Code change with no behaviour change | `refactor: extract _build_query helper` |
| `perf` | Performance improvement | `perf: cache snapshot reads` |
| `chore` | Maintenance, dependencies, CI | `chore: bump requests to 2.32` |
| `ci` | CI/CD changes | `ci: add Python 3.14 to test matrix` |

**Rules:**
- Use the imperative mood: "add" not "added" or "adds"
- First line ≤ 72 characters
- Reference issues in the footer: `Closes #42` or `Refs #17`
- One logical change per commit — don't bundle unrelated fixes

---

## Pull Request Checklist

Before marking your PR ready for review:

- [ ] All existing tests pass (`pytest tests/ -v`)
- [ ] New behaviour is covered by new tests
- [ ] Docstrings added/updated for any modified public functions
- [ ] Type hints present on all function signatures
- [ ] `--help` output updated if new CLI flags were added
- [ ] README updated if the change affects user-visible behaviour
- [ ] CHANGELOG entry added under `[Unreleased]`
- [ ] Commit messages follow the convention above
- [ ] PR description explains **what** changed and **why**

---

## Reporting Bugs

Open a [GitHub Issue](https://github.com/alisadeghiaghili/daily-github-pulse/issues/new) and include:

1. **Python version** — `python --version`
2. **OS** — e.g. Ubuntu 22.04, macOS 14, Windows 11
3. **Full command** you ran (redact your token)
4. **Full error output** — paste the complete traceback
5. **Steps to reproduce** — minimal, numbered steps
6. **Expected behaviour** vs **actual behaviour**

If you can, include the output of:
```bash
python github_repo_of_the_day.py --version
```

---

## Suggesting Features

Open a [GitHub Issue](https://github.com/alisadeghiaghili/daily-github-pulse/issues/new) and include:

1. **Problem statement** — what are you trying to do that you can't do today?
2. **Proposed solution** — what would you like to see?
3. **Alternatives considered** — what workarounds exist?
4. **CLI mockup** — show what the new flag or output would look like

Feature requests that include a CLI mockup and a clear problem statement are much more likely to be accepted.

---

## Code Style

- **PEP 8** — use a linter (`ruff` or `flake8`)
- **Type hints** on all function signatures — `def foo(x: str) -> list[str]:`
- **Docstrings** on all public functions and classes (Google style preferred)
- **Single-purpose functions** — if a function does two things, split it
- **No magic numbers** — use named constants (see `PERIOD_DAYS`, `VALID_SEARCH_IN`)
- **Errors early** — validate inputs at the top of functions, raise `ValueError` with clear messages
- **Tests for every new branch** — if you add an `if`, add a test for both paths

```python
# Good
def build_keyword_qualifier(
    keywords: list[str],
    keyword_op: str = "AND",
    search_in: str = "name,description",
) -> str:
    """Build a GitHub Search qualifier string from a list of keywords.

    Args:
        keywords:   List of keyword strings.
        keyword_op: Boolean operator joining keywords. Must be AND or OR.
        search_in:  Comma-separated search scope tokens.

    Returns:
        A GitHub Search qualifier string.

    Raises:
        ValueError: If keyword_op is not AND or OR.
        ValueError: If any search_in token is invalid.
    """
    ...
```

---

Thank you for contributing! Every bug report, feature idea, and pull request makes this project better. 🙌
