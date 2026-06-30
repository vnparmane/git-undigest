# git-undigest

[![PyPI](https://img.shields.io/pypi/v/git-undigest)](https://pypi.org/project/git-undigest/)
[![Python](https://img.shields.io/pypi/pyversions/git-undigest)](https://pypi.org/project/git-undigest/)
[![License](https://img.shields.io/pypi/l/git-undigest)](LICENSE)
[![CI](https://github.com/vnparmane/git-undigest/actions/workflows/ci.yml/badge.svg)](https://github.com/vnparmane/git-undigest/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)

Reconstruct a full repository — folder structure and all — from a
[GitIngest](https://gitingest.com)-style digest file.

GitIngest turns a repository into a single flat text digest for feeding to
an LLM. `git-undigest` does the reverse: it parses that digest and rebuilds
the original directory tree and files on disk, safely and deterministically.

---

## Features

- **Streaming parser** — parses multi-GB digests with constant memory
  (proportional to the largest single file, not total size).
- **Pluggable formats** — add support for Repomix, Repopack, or custom digest
  formats without modifying core code.
- **Security-first** — path traversal protection, absolute path rejection,
  Windows reserved name detection, atomic writes.
- **Conflict handling** — `--overwrite`, `--skip-existing`, `--backup` policies.
- **Dry-run mode** — preview what would happen without touching the filesystem.
- **Compressed digests** — transparent `.gz`, `.xz` support built-in;
  `.zst` via `pip install git-undigest[zstd]`.
- **Plugin discovery** — third-party format packages auto-discovered via
  entry points.
- **No runtime dependencies** — pure Python, zero required installs beyond
  the standard library.

## Installation

```bash
pip install git-undigest
```

Requires Python 3.10+.

Optional compression support:

```bash
pip install "git-undigest[zstd]"    # for .zst (zstandard) files
```

## Quick Start

```bash
# Reconstruct a repository from a digest file
git-undigest digest.txt

# Reconstruct into a specific directory
git-undigest digest.txt output/

# Validate without writing
git-undigest validate digest.txt
```

## CLI Examples

```bash
# Reconstruct with overwrite policy
git-undigest digest.txt --overwrite

# Dry-run preview
git-undigest digest.txt output/ --dry-run

# Skip files that already exist
git-undigest digest.txt output/ --skip-existing

# Back up existing files before overwriting
git-undigest digest.txt output/ --backup

# Verbose output (one line per file action)
git-undigest digest.txt --verbose

# Inspect repository metadata
git-undigest inspect digest.txt

# List all files in the digest
git-undigest list digest.txt

# Get statistics
git-undigest stats digest.txt
```

### Conflict Flags

| Flag | Behavior |
|------|----------|
| `--overwrite` | Overwrite existing files instead of erroring |
| `--skip-existing` | Leave existing files untouched |
| `--backup` | Rename existing files to `name.bak` before writing |
| `--dry-run` | Show what would happen without touching the filesystem |
| `--verbose` | Print a line for every file action taken |
| `--quiet` | Suppress summary output |

## Python API

```python
from git_undigest import reconstruct, validate, inspect, stats, list_files

# Reconstruct a repository
result = reconstruct("digest.txt", output="repo")
print(f"{len(result.created)} files created in {result.output_dir}")

# Validate without writing
summary = validate("digest.txt")
print(f"Repository: {summary.repo_name}, {summary.file_count} files")

# Inspect
info = inspect("digest.txt")
print("Languages:", info["languages"])
print("Directory tree:\n", info["tree"])

# Get statistics
s = stats("digest.txt")
print(f"Total: {s.total_bytes} bytes, ~{s.estimated_tokens} tokens")

# List all files
for path in list_files("digest.txt"):
    print(path)
```

### Streaming API

For large digests, use the streaming parser directly:

```python
from git_undigest import parse_stream, reconstruct_files_stream

entries = parse_stream("large_digest.txt")
result = reconstruct_files_stream(entries, "output", overwrite=True)
```

This keeps memory constant regardless of digest size.

## Supported Digest Formats

| Format | Status | Notes |
|--------|--------|-------|
| GitIngest | Stable | Default format |
| Custom | Pluggable | Subclass `DigestFormat` |

To add support for a new format, create a subclass of `DigestFormat`,
implement `sniff()`, `parse_stream()`, and `serialize()`, then register it:

```python
from git_undigest.formats import DigestFormat, register_format_class
from git_undigest.models import FileEntry

class MyFormat(DigestFormat):
    name = "myformat"

    @classmethod
    def sniff(cls, prefix: str) -> bool:
        return prefix.startswith("MAGIC")

    def parse_stream(self, stream):
        ...  # yield FileEntry instances

    def serialize(self, repo) -> str:
        ...

register_format_class(MyFormat)
```

Third-party packages are auto-discovered via the `git_undigest.formats`
entry point group.

## Security

Every path in the digest is validated before anything is written:

- **No path traversal.** `../../../etc/passwd`, `../secret.txt`, and any
  path containing a `..` segment that would escape the output directory
  is rejected with `PathTraversalError`.
- **No absolute paths.** POSIX absolute paths (`/etc/shadow`), Windows
  drive-qualified paths (`C:\Windows\System32`), and UNC paths
  (`\\server\share`) are all rejected.
- **No Windows reserved device names.** `CON`, `PRN`, `AUX`, `NUL`,
  `COM1`–`COM9`, `LPT1`–`LPT9` are rejected as path components.
- **No null bytes** are permitted in paths.
- **Final containment check.** Every resolved path is confirmed, via
  `Path.relative_to`, to be a real descendant of the output directory
  after full filesystem resolution.
- **Atomic writes.** Files are written to a temporary file in the same
  directory and then renamed into place, so a crash or interruption never
  leaves a partially-written file at the destination.

## Architecture

```
src/git_undigest/
├── __init__.py       # Public API: reconstruct, validate, inspect, stats
├── cli.py            # argparse CLI entry point
├── parser.py         # Streaming and bulk digest parsing
├── formats/
│   ├── __init__.py   # DigestFormat ABC, registry, plugin discovery
│   └── gitingest.py  # GitIngest format implementation
├── validator.py      # Path safety + structural validation
├── writer.py         # Streaming filesystem reconstruction
├── checksum.py       # SHA-256 checksum utilities
├── models.py         # Dataclasses (FileEntry, Repository, results)
├── exceptions.py     # Exception hierarchy
└── utils.py          # Shared helpers

benchmarks/
└── bench_streaming.py
tests/
├── test_api.py
├── test_cli.py
├── test_parser.py
├── test_writer.py
├── test_validator.py
├── test_fuzz.py
├── test_phase1.py
├── test_formats_and_placeholders.py
└── ...
```

### Design Principles

- **Parser only parses.** It never touches the filesystem or makes security
  decisions.
- **Writer only writes.** It assumes the digest has been validated, but
  re-validates every path as defense-in-depth.
- **Validator owns all validation.** No duplicated logic.
- **Formats are pluggable.** Adding a new format means a new module in
  `formats/` — no changes to `parser.py`, `validator.py`, or `writer.py`.
- **Streaming by default.** All public APIs use constant-memory streaming
  internally.

## Performance

The streaming parser is 2–30x faster than bulk parsing for typical digest
sizes because it avoids allocating a single large string for the entire
digest:

| Files | Digest Size | Bulk (s) | Stream (s) | Speedup |
|-------|-------------|----------|------------|---------|
| 100   | 12 KB       | 0.036    | 0.001      | 32x     |
| 1,000 | 120 KB      | 0.040    | 0.007      | 6x      |
| 10,000| 1.2 MB      | 0.124    | 0.072      | 1.7x    |

Memory usage is O(largest file) for streaming vs O(total digest) for bulk.

## Roadmap

- [ ] SHA-256 checksum manifest verification
- [ ] Binary file reconstruction (base64-embedded digests)
- [ ] Parallel reconstruction for very large digests
- [ ] Resumable reconstruction
- [ ] Plugin distribution guide for third-party format packages

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing
instructions, and pull request guidelines.

## License

MIT — see [LICENSE](LICENSE).
