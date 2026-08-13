## 2025-02-12 - Prevent process listing leaks
**Vulnerability:** Tokens could be passed via CLI arguments (`--token`, `--gitlab-token`, `--gitea-token`), exposing them in process lists.
**Learning:** Process listing leaks can compromise sensitive credentials provided as arguments.
**Prevention:** Only use environment variables (`.env`) for sensitive credentials and API tokens.
