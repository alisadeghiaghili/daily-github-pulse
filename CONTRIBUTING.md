# Contributing

Contributions are welcome! Please follow these steps:

## Getting Started

1. Fork the repository
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes
4. Run a quick smoke test:
   ```bash
   python github_repo_of_the_day.py --top 3
   ```
5. Commit with a clear message:
   ```bash
   git commit -m "feat: add JSON output flag"
   ```
6. Push and open a Pull Request

## Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | When to use |
|--------|-------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code change, no feature/fix |
| `chore:` | Maintenance, dependencies |

## Code Style

- Follow PEP 8
- Add docstrings to all public functions
- Keep functions small and single-purpose
- Type-hint all function signatures

## Reporting Issues

Open an issue with:
- Python version (`python --version`)
- OS
- Full error output
- Steps to reproduce
