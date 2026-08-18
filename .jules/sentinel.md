## 2025-02-14 - Process Listing Credential Exposure
**Vulnerability:** API tokens could be passed as CLI arguments (e.g., `--token`, `--gitlab-token`), exposing sensitive credentials to other users on the system via process listing utilities like `ps -ef` or `top`.
**Learning:** Command line arguments are generally readable by all users on a Unix-like system. Accepting secrets this way is a major security flaw.
**Prevention:** Always require sensitive credentials to be provided via environment variables, `.env` files, or secure vaults, and never through command line arguments.
