# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [1.8.0] - 2026-06-02

### Added
- **`build_keyword_qualifier()`** — new pure function that composes a GitHub
  Search keyword fragment from one or more terms, a boolean operator, optional
  exclusions, and a scope qualifier:
  - Each term (positive or negative) is wrapped in `"double quotes"` so
    multi-word phrases are exact-matched and the `in:` scope applies to the
    whole phrase, not just the last token.
  - Terms are joined with `" AND "` or `" OR "` (controlled by `keyword_op`).
  - The `in:<search_in>` qualifier is appended exactly **once**, regardless
    of how many keywords are provided.
  - Exclusion terms are appended as `NOT "term"` after the positive block.
  - `keywords=[]` returns `""` (empty list → browse mode).
  - `keyword_op` is normalised to uppercase; leading/trailing whitespace
    stripped.  Invalid values raise `ValueError` listing `AND` and `OR`.
  - Delegates `search_in` validation to the existing `VALID_SEARCH_IN` set.
- **`search_trending_repos()`** — three new parameters:
  - `keywords: list[str]` — multi-keyword list; replaces the legacy `keyword`
    string for boolean search.  Empty list falls back to browse mode.
  - `keyword_op: str` — boolean connector, `"AND"` (default) or `"OR"`.
  - `keyword_not: list[str]` — exclusion terms; each becomes a `NOT "term"`
    clause in both generated queries.
  - `keyword` (legacy single-string param) is preserved for full backward
    compatibility.  Supplying both `keyword` and `keywords` raises `ValueError`.
- **`find_repo_of_the_day()`** updated to accept and pass through the new
  `keywords`, `keyword_op`, and `keyword_not` parameters.  Header now prints
  the full boolean expression and exclusions when `keywords` is used.
- **CLI flags**:
  - `--keywords WORD [WORD ...]` — one or more search terms (nargs=`+`).
    Mutually exclusive with `--keyword`.
  - `--keyword-op {AND,OR}` — connector between terms (default: `AND`).
  - `--keyword-not WORD [WORD ...]` — terms to exclude (NOT clauses).
- **`VALID_KEYWORD_OPS`** constant — single source of truth: `{"AND", "OR"}`.
- Version bumped `1.7.0 → 1.8.0`.

### Tests
- **`TestBuildKeywordQualifier`** — 25 new TDD tests covering:
  single keyword quoting, multi-word phrase handling, default `in:` scope,
  AND joining (2 and 3 terms), OR joining (2 and 3 terms),
  `keyword_op` case-insensitivity and whitespace normalisation,
  invalid `keyword_op` `ValueError`,
  single/multiple `keyword_not` terms, NOT placement after positive block,
  multi-word NOT phrase quoting, empty `keyword_not` produces no NOT clause,
  AND+NOT and OR+NOT combinations,
  empty keywords list returns `""`, NOT-only (empty positive) returns `""`,
  leading/trailing whitespace stripped from terms,
  `in:` qualifier appears exactly once,
  invalid `search_in` raises `ValueError`.
- **`TestSearchTrendingReposMultiKeyword`** — 9 new integration tests covering:
  AND query shape, OR query shape, `keyword_not` NOT clause in both queries,
  multi-keyword triggers search mode categories,
  time filter preserved with multiple keywords,
  `in:` qualifier appears exactly once per query,
  `keyword` + `keywords` together raises `ValueError`,
  empty `keywords=[]` falls back to browse mode,
  single-item list equivalent to legacy `keyword`.

---

## [1.5.0] - 2026-06-01

### Added
- **`elapsed_days()`** — new pure function that parses the `saved_at` UTC
  timestamp stored in each snapshot entry and returns the number of
  fractional days elapsed since that save.  Handles both timezone-aware
  (v1.5.0+) and naive UTC (legacy v1.x) timestamps.  Returns `None` for
  missing, blank, or unparseable timestamps.  Guards against clock-skew /
  same-second saves with a minimum floor of `1/86400` days.
- **`daily_velocity()`** — new pure function computing the time-normalised
  star growth rate: `star_delta / elapsed_days`, rounded to one decimal
  place.  A repo that gained 1 400 stars over 14 days reports `100.0`,
  the same as one that gained 100 stars in 24 hours — the number stays
  meaningful regardless of how long ago the snapshot was taken.
- **`daily_velocity` field** added to `EXPORT_FIELDS` and surfaced in
  JSON / CSV exports (`null` / empty on first run).
- **Updated `format_velocity()`** — signature changed from
  `format_velocity(delta)` to `format_velocity(delta, velocity)`.  Output
  now shows both the raw total (`+700 ⭐ total`) and the normalised rate
  (`~100.0 ⭐/day`) side-by-side.
- **Updated `format_repo()`** — passes `daily_velocity()` result to the
  new `format_velocity()` signature.
- **Updated `build_export_row()`** — includes `daily_velocity` field.
- **Updated `save_snapshots()`** — now writes timezone-aware UTC
  timestamps (`datetime.now(timezone.utc)`) instead of naive UTC, so
  `elapsed_days()` can always compute an accurate interval.
- Version bumped `1.4.0 → 1.5.0`.

### Tests
- **`TestElapsedDays`** — 7 new tests:
  missing repo, missing `saved_at`, invalid timestamp, ~1 day, ~7 days,
  legacy naive UTC timestamp, same-second floor guard.
- **`TestDailyVelocity`** — 7 new tests:
  no snapshot, velocity over 2 days, velocity over 7 days,
  normalisation-independent-of-gap proof, zero delta, negative velocity,
  one-decimal rounding.
- **`TestFormatVelocity`** updated — asserts `⭐/day` and `total` labels;
  covers `None`-delta-only edge case.
- **`TestFormatRepo`** updated — asserts both `+delta` and `⭐/day` when
  snapshot is present.
- **`TestSaveSnapshots`** — new `test_saved_at_is_utc_iso_string` test
  verifying timestamps are timezone-aware.
- **`sample_snapshots` fixture** updated — `saved_at` is now a real
  timestamp 2 days in the past (not a static string) so velocity tests
  produce deterministic approximate values.

---

## [1.4.1] - 2026-06-01

### Added
- **GitHub Actions CI workflow** (`.github/workflows/tests.yml`) —
  runs `pytest` automatically on every push and pull request to `main`
  across a matrix of **Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14**
  (`fail-fast: false` so all versions are always reported).
- **Telegram notification** — a `notify` job runs after the test matrix
  and sends a ✅/❌ message with branch, commit, actor, and a direct link
  to the Actions run. Triggered only when `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` secrets are configured; skips silently otherwise.
- **CI badge** added to `README.md` header.
- **CI section** added to `README.md` explaining the pipeline and
  Telegram secret setup.

---

## [1.4.0] - 2026-06-01

### Added
- **`--period` / `-p`** flag — named look-back window shortcut:
  `day` (1 day), `week` (7 days), `month` (30 days).
  Takes precedence over `--days` when both are supplied.
- `resolve_period()` — pure function mapping period token → days integer.
  Case-insensitive, strips leading/trailing whitespace, raises `ValueError`
  for unknown tokens with a descriptive message listing valid options.
- `PERIOD_DAYS` constant — single source of truth mapping
  `{"day": 1, "week": 7, "month": 30}`.
- `--days` help text updated to note it is ignored when `--period` is used.

### Tests
- `TestResolvePeriod` — 12 new tests covering all tokens, case-insensitivity,
  whitespace handling, precedence over `--days`, and invalid token errors.

---

## [1.3.0] - 2026-06-01

### Added
- **`--output` / `-o`** flag — choose output format: `text` (default), `json`, `csv`.
- **`--output-file` / `-f`** flag — write JSON or CSV to a file instead of stdout.
- `build_export_row()` — builds a flat, renamed export record per repo.
- `export_json()` — serialises rows to a pretty-printed JSON string.
- `export_csv()` — serialises rows to a CSV string with `utf-8-sig` BOM
  (opens correctly in Excel / LibreOffice without manual encoding setup).
- `write_output()` — routes content to file or stdout; confirmation printed to stderr.
- `EXPORT_FIELDS` constant — defines the canonical ordered column list for exports.
- `star_delta` field included in all exports (`null` / empty on first run).

### Changed
- `find_repo_of_the_day()` accepts two new parameters: `output_fmt` and `output_file`.
- Header and separator lines are suppressed in JSON/CSV mode (written to stderr only).
- Error messages now always print to stderr (not stdout), so they never contaminate
  piped JSON/CSV output.

---

## [1.2.0] - 2026-06-01

### Added
- **Star velocity** — on each run, star counts are saved to
  `~/.daily-github-pulse/snapshots.json`. On subsequent runs the delta
  (e.g. `+142 ⭐ since last run`) is displayed next to each repo.
- `--no-snapshot` flag — skip loading/saving snapshots for a single run.
- `--clear-snapshots` flag — delete all stored snapshot data and exit.
- `--version` flag — print current version and exit.
- Improved error handling with distinct messages for HTTP errors,
  connection failures, and timeouts.

### Changed
- `format_repo()` now accepts a `snapshots` dict and renders velocity line.
- Header now shows velocity status (`enabled` / `disabled`).

---

## [1.1.0] - 2026-06-01

### Added
- `--keyword` / `-k` flag — search a keyword across repo metadata.
- `--search-in` / `-s` flag — control where the keyword is searched:
  `name`, `description`, `readme`, or any comma-separated combination.
  Default: `name,description`.
- Cross-category deduplication — repos returned by both `New Today` and
  `Active Giants` are now shown only once (in the first category).
- Token loading via `.env` file using `python-dotenv` (optional dependency).

---

## [1.0.0] - 2026-06-01

### Added
- Initial release.
- Two-strategy GitHub search: `New Today` and `Active Giants`.
- CLI flags: `--language`, `--days`, `--top`, `--token`.
- Human-readable formatted output with stars, forks, language, dates, and URL.
- Auth status indicator in output header.
