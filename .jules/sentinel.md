## 2026-08-10 - [Remove tokens from CLI arguments]
**Vulnerability:** API tokens could be passed as command line arguments (e.g. `--token`), which are visible to all users on a multi-user system via commands like `ps aux`.
**Learning:** Even though overriding environment variables via CLI flags seems convenient, it poses a significant security risk for secrets.
**Prevention:** Always require secrets to be loaded via environment variables or secure configuration files like `.env` instead of command line flags.
