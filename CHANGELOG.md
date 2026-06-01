# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
