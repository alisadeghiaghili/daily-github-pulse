## 2024-08-20 - [Removed CLI token arguments to prevent credential leakage]
**Vulnerability:** The application accepted authentication tokens via CLI arguments (`--token`, `--gitlab-token`, `--gitea-token`).
**Learning:** Accepting sensitive credentials via CLI arguments exposes them to process listing (`ps -ef`) and bash history, leading to potential credential leakage on shared systems.
**Prevention:** Always provide sensitive credentials and API tokens via environment variables or a `.env` file, and avoid using command-line arguments.
