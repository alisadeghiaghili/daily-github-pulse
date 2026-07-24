# Changelog

All notable changes to **daily-github-pulse** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [3.0.0] — 2026-07-24

### Added
- **Multi-forge support** — browse trending repos and developers across GitHub, GitLab, Gitea/Codeberg, and Bitbucket
- **`forges/` package** — forge abstraction layer with `ForgeClient` ABC and per-forge implementations:
  - `forges/base.py` — `ForgeClient` ABC + `ForgeRepo`/`ForgeUser` dataclasses
  - `forges/github.py` — GitHub REST API v3 client
  - `forges/gitlab.py` — GitLab REST API v4 client
  - `forges/gitea.py` — Gitea/Codeberg REST API v1 client
  - `forges/bitbucket.py` — Bitbucket REST API v2.0 client
- **`--forge` CLI flag** — specify forge(s) to search, comma-separated for multi-forge
- **`--gitea-url` CLI flag** — custom Gitea instance URL (e.g. Codeberg)
- **`--gitlab-token` / `--gitea-token` CLI flags** — per-forge auth tokens
- **Multi-forge parallel search** — searches multiple forges concurrently via `ThreadPoolExecutor`
- **Merged & ranked output** — multi-forge results sorted by stars with visible forge labels
- **Forge column in exports** — JSON/CSV exports now include a `forge` field
- **Forge labels in Rich tables** — color-coded forge badges (GitHub=white, GitLab=red, Gitea=green, Bitbucket=blue)
- **`daily_github_pulse.py`** — new main entry point for multi-forge support
- **Forge-specific tests** — 37 new tests across `test_github.py`, `test_gitlab.py`, `test_gitea.py`, `test_bitbucket.py`

### Changed
- `github_repo_of_the_day.py` — now serves as backward-compat alias, version bumped to 3.0.0
- `rich_display.py` — `print_repo_table()` and `print_developer_table()` now support ForgeRepo/ForgeUser objects with forge labels
- `requirements.txt` — updated with multi-forge documentation and `pytest-cov` in dev section
- `CONTRIBUTING.md` — updated project structure to reflect forge architecture

### Fixed
- Added `UnicodeDecodeError` handling in `fetch_readme_snippet()` for non-text READMEs
- Fixed `_capture_console()` in tests to use `rd.console` instead of `rd._console`
- Removed unused `_mock_user_response()` test helper
- Added type hints: `_build_arg_parser()` return type, `BoolNode.children` type
- Wired up `make_ai_filter_progress()` in AI filter path

### Removed
- Removed unused `_mock_user_response()` from test suite

---

## [2.3.0] — 2026-06-13

### Added
- **`rich_display.py`** — full Rich-powered terminal renderer as an optional drop-in:
  - `print_header(since_days, mode)` — styled Panel header with cyan border
  - `print_repo_table(repos_by_category, snapshots)` — rounded table with columns: rank, repo (clickable link), stars, Δ stars (green/red), forks, language (colour-coded per language), description
  - `print_developer_table(developers)` — rounded table with followers, repos, company, location, bio
  - `make_ai_filter_progress()` — Rich Progress bar for AI filtering stage
  - `format_velocity_markup(delta, velocity)` — Rich markup helper for delta / velocity cells
  - Language → colour mapping for 20+ languages (Python → yellow, Rust → red, Go → cyan, …)
  - Graceful no-op fallback when `rich` is not installed — plain-text output unchanged
- **`tests/test_rich_display.py`** — 40 new tests covering all public functions in `rich_display.py`:
  - `RICH_AVAILABLE` flag detection
  - `format_velocity_markup` — None (first run), positive, negative, zero, with/without velocity
  - `print_header` — rich and fallback paths, stdout vs stderr routing
  - `print_repo_table` — table rendered, clickable links, colour badges, delta colours, empty category
  - `print_developer_table` — all columns, missing fields fallback, clickable login links
  - `make_ai_filter_progress` — returns Progress instance vs None

### Changed
- `requirements.txt` — `rich>=13.7.0` promoted to a **recommended** (soft) dependency with clear inline comments for every optional group
- `README.md` / `README.en.md` / `README.de.md` — updated Quick Start, features table, and test count (now 176 tests)
- Version bumped to `2.3.0`

---

## [2.0.0] — 2026-06-02

### Added
- **Wildcard expansion** (`--wildcard` flag) for `--keywords`:
  - `?` matches exactly one character — `analy?e` → `analyse OR analyze`
  - `*` matches zero or more characters — `optimiz*` → `optimize OR optimized OR optimizing …`
  - Expansion is done client-side against the NLTK English words corpus
  - Corpus is auto-downloaded on first `--wildcard` run (`nltk` optional dependency)
  - Graceful fallback: if `nltk` is not installed, term is passed through unchanged — no crash
  - Max 20 variants per wildcard pattern to prevent query explosion
- New public functions: `expand_wildcards()`, `apply_wildcards_to_keywords()`, `_load_wordlist()`
- Header now prints `Wildcard : enabled` when `--wildcard` is active
- `requirements.txt` documents `nltk` as optional dependency

### Changed
- `find_repo_of_the_day()` accepts new `wildcard: bool = False` parameter
- Version bumped to `2.0.0`

---

## [1.9.0] — 2026-06-01

### Added
- `--bool-query` flag: full Boolean expression parser with `AND`, `OR`, `NOT`, and parentheses
- AST types `Term` and `BoolNode` with full docstrings and examples
- `parse_boolean_query()` — recursive-descent parser
- `_serialise_node()` — AST → GitHub query fragment serialiser
- `build_keyword_qualifier()` extended to accept `Term` / `BoolNode` directly (AST path)
- `--keyword-not` flag: exclude terms via `NOT "term"` clauses

### Changed
- Version bumped to `1.9.0`

---

## [1.8.0] — 2026-06-01

### Added
- `--keywords` (multi-keyword list) + `--keyword-op` (AND / OR connector)
- `build_keyword_qualifier()` helper centralises all keyword → GitHub query logic
- `_validate_search_in()` validates `--search-in` tokens up-front
- Mutual-exclusion guard: `--keyword` vs `--keywords` vs `--bool-query`

### Changed
- Version bumped to `1.8.0`

---

## [1.2.0] — 2026-06-01

### Added
- **Star velocity** — time-normalised daily star growth rate (`daily_velocity`)
- `elapsed_days()` helper for time-normalised velocity calculation
- `snapshots.json` stores UTC `saved_at` timestamps alongside star counts
- `format_velocity()` displays both raw delta and stars-per-day
- `--no-snapshot` flag to skip snapshot I/O for a single run
- `--clear-snapshots` flag to delete stored snapshot file

### Changed
- Version bumped to `1.2.0`

---

## [1.1.0] — 2026-06-01

### Added
- `--keyword` / `-k` single-keyword search against repo name and description
- `--search-in` / `-s` scope selector: `name`, `description`, `readme`
- Search mode switches to higher star thresholds (`>50` new, `>500` active)
- Deduplication across category buckets via `seen_ids` set

### Changed
- Version bumped to `1.1.0`

---

## [1.0.0] — 2026-06-01

### Added
- Initial release
- Browse mode: **New Today** (created today, >10 stars) and **Active Giants** (pushed today, >1000 stars)
- `--language` / `-l` language filter
- `--days` / `-d` look-back window (default: 1)
- `--period` shortcut: `day`, `week`, `month`
- `--top` / `-n` result count per category
- `--output` formats: `text` (default), `json`, `csv`
- `--output-file` to write exports to disk
- `--token` CLI override for GitHub PAT
- `.env` support via `python-dotenv`
- Snapshot-based star delta tracking (`~/.daily-github-pulse/snapshots.json`)
- Trending developers mode (`--developers`)
- Full docstrings, type hints, and `--version` flag
