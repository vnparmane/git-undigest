# Contributing to git-undigest

Thank you for your interest in contributing! This document provides
guidelines and instructions for setting up a development environment,
running tests, and submitting changes.

## Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/anomalyco/git-undigest.git
   cd git-undigest
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   .venv\Scripts\activate      # Windows
   ```

3. **Install in editable mode with dev dependencies:**

   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
python -m pytest
```

Run with coverage:

```bash
python -m pytest --cov=git_undigest
```

To run a specific test file:

```bash
python -m pytest tests/test_parser.py -v
```

Run the streaming benchmark:

```bash
python benchmarks/bench_streaming.py
```

## Code Quality

We use **ruff** for linting and **black** for formatting.

```bash
# Lint
python -m ruff check .

# Format
python -m black src/ tests/ benchmarks/

# Type check
python -m mypy src/ --strict
```

All three must pass before a pull request is accepted. The CI pipeline
enforces these checks automatically.

## Pull Request Guidelines

1. Fork the repository and create a feature branch.
2. Write tests for any new functionality.
3. Ensure all existing tests pass.
4. Run lint, format, and type-check commands above.
5. Keep pull requests focused on a single concern.
6. Update documentation and CHANGELOG.md as needed.
7. Open the pull request against the `main` branch.

## Commit Style

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add streaming digest parser
fix: handle empty separator at EOF
docs: update CLI examples in README
refactor: extract format detection logic
test: add fuzz tests for corrupted input
chore: update ruff configuration
```

Prefixes: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`,
`perf`, `style`.

## Project Structure

```
src/git_undigest/
├── __init__.py       # Public API
├── cli.py            # CLI entry point
├── parser.py         # Digest parsing
├── formats/          # Digest format plugins
│   ├── __init__.py   # Format registry + DigestFormat ABC
│   └── gitingest.py  # GitIngest format
├── validator.py      # Path + structural validation
├── writer.py         # Filesystem reconstruction
├── checksum.py       # SHA-256 helpers
├── models.py         # Dataclasses
├── exceptions.py     # Exception hierarchy
└── utils.py          # Shared utilities

benchmarks/           # Performance benchmarks
tests/                # Test suite
```

## Questions?

Open a [discussion](https://github.com/anomalyco/git-undigest/discussions)
or [issue](https://github.com/anomalyco/git-undigest/issues).
