# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] — 2026-07-01

### Fixed

- Corrected package author metadata displayed on PyPI.
- Minor metadata cleanup.

## [0.2.0] — 2026-06-30

### Added

- Streaming parser (`parse_stream`) — parses digests in constant memory
  proportional to the largest single file, not the total digest size.
- Streaming writer pipeline (`reconstruct_files_stream`) with integrated
  validation — parses, validates, and writes in one pass.
- `DigestFormat` ABC for pluggable digest format support:
  - `sniff(prefix)` detects format from the first ~8 KB.
  - `parse_stream()` yields `FileEntry` objects one at a time.
  - `_FunctionBasedFormat` adapter for backward-compatible function-based
    plugins.
- `validate_entries_stream()` — streaming path validation with duplicate
  detection.
- `Repository` canonical model with `FileEntry` — `FileEntry.to_digest_file()`,
  `DigestSummary.to_repository()`, `Repository.to_digest_summary()`.
- Plugin discovery via `importlib.metadata` entry points
  (`git_undigest.formats` group).
- Optional `zstandard` support for `.zst` compressed digests
  (`pip install git-undigest[zstd]`).
- Zstandard compression support with graceful error when package missing.
- CLI — `reconstruct`, `validate`, `inspect`, `list`, `stats` subcommands.
- `--dry-run`, `--overwrite`, `--skip-existing`, `--backup` flags.
- Atomic file writes (write-temp + rename).
- Path traversal protection — absolute paths, drive letters, UNC paths,
  reserved names, null bytes, and `..` escape.
- Duplicate file detection.
- Support for compressed digest formats (`.gz`, `.xz`, `.zst`).
- `benchmarks/bench_streaming.py` — streaming vs bulk parse performance
  comparison.
- Fuzz tests for malformed, random, corrupted, and boundary-case input.

### Changed

- `parse()` now delegates to `parse_stream()` by default — single code path.
- `GitIngestFormat.parse()` rewritten to delegate to `parse_stream()`.
- `reconstruct()` now uses streaming internally.
- `reconstruct_files()` streams through the writer pipeline.
- File opened twice for streaming: once for format sniffing (8 KB prefix),
  then again for line-by-line streaming.

### Fixed

- Trailing separator at end of digest no longer creates phantom entries.
- State machine correctly handles first file header in state 0.
- Windows reserved device name detection (`CON`, `NUL`, etc.).

### Removed

- `_parse_stream_lines()` — all parsing unified into `parse_stream()`.
- `peek` + `StringIO` pattern — replaced by two-open streaming.

## [0.1.0] — 2024-12-15

### Added

- Initial proof-of-concept.
- `parse_digest()` — basic GitIngest digest parser.
- `reconstruct()` — reconstruct files from a parsed digest.
- `validate()` — structural and security validation.
- `inspect()`, `stats()`, `list_files()` — digest inspection.
- CLI with reconstruct and validation commands.
- MIT license.
