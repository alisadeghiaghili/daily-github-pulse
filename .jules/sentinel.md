## 2024-05-18 - Prevent Token Leaks via Process Listing
**Vulnerability:** Passing authentication tokens (like GITHUB_TOKEN) via command line arguments (`--token`, `--gitlab-token`, `--gitea-token`).
**Learning:** Command line arguments are visible to any user on the system running `ps aux` or viewing `/proc/<pid>/cmdline`. This exposes sensitive credentials.
**Prevention:** Remove token arguments from CLI interfaces and enforce loading tokens securely from environment variables or `.env` files.
