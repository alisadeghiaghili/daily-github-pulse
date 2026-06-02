# Changelog

All notable changes to **daily-github-pulse** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
