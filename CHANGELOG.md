# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
