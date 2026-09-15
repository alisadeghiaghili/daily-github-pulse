## 2023-10-25 - [Process Listing Leak]
**Vulnerability:** Insecure CLI arguments used for passing sensitive tokens (e.g. `--token`, `--gitlab-token`, `--gitea-token`) could leak credentials to other users on the system via process listings (like `ps aux`).
**Learning:** Hardcoding or passing API tokens through command line arguments is a common anti-pattern that exposes secrets system-wide.
**Prevention:** Use environment variables instead of CLI flags for sensitive tokens. Hide legacy insecure CLI arguments using `argparse.SUPPRESS` and emit a clear warning to `sys.stderr` when they are used to gently enforce deprecation without breaking backwards compatibility.
