"""Filesystem reconstruction logic.

The writer's only job is to materialise a repository on disk from an
iterable of :class:`FileEntry` objects, honouring overwrite policy,
backup, and dry-run options.

All public APIs in this module use streaming internally — they never
build a list of every file in memory.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from .exceptions import (
    FileExistsConflictError,
    FileWriteError,
    NotImplementedFeatureError,
)
from .models import (
    DigestSummary,
    FileEntry,
    ReconstructionResult,
    Repository,
    WriteResult,
)
from .validator import validate_entries_stream, validate_safe_path

# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------


def _atomic_write(target: Path, content: str) -> int:
    """Write ``content`` to ``target`` atomically (write-temp + rename).

    Args:
        target: Final destination path. Parent directories must already
            exist.
        content: Text content to write, UTF-8 encoded.

    Returns:
        Number of bytes written.

    Raises:
        FileWriteError: If the write or rename fails.
    """
    data = content.encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise FileWriteError(f"Failed to write {target}: {exc}") from exc
    return len(data)


def _atomic_write_bytes(target: Path, data: bytes) -> int:
    """Write raw ``data`` to ``target`` atomically (write-temp + rename)."""
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise FileWriteError(f"Failed to write {target}: {exc}") from exc
    return len(data)


def _next_backup_path(target: Path) -> Path:
    """Compute a non-colliding ``*.bak`` path for ``target``."""
    candidate = target.with_name(target.name + ".bak")
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = target.with_name(f"{target.name}.bak.{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Binary reconstruction
# ---------------------------------------------------------------------------


def _decode_binary_content(content: str) -> bytes:
    """Decode a base64-encoded binary string."""
    from .exceptions import BinaryDecodeError

    stripped = content.strip()
    try:
        return base64.b64decode(stripped, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise BinaryDecodeError("Invalid base64 content") from exc


def reconstruct_binary_file(
    target: Path,
    base64_content: str,
    *,
    max_size: int = 100 * 1024 * 1024,
) -> int:
    """Reconstruct a binary file from base64-encoded content.

    Args:
        target: Destination path for the decoded binary file.
        base64_content: Base64-encoded content string.
        max_size: Maximum allowed decoded size in bytes (default 100 MB).

    Returns:
        Number of bytes written.
    """
    from .exceptions import FileSizeLimitError

    if len(base64_content) > max_size * 4 // 3 + 4:
        raise FileSizeLimitError(
            f"Base64 payload would exceed maximum size of {max_size} bytes"
        )

    data = _decode_binary_content(base64_content)

    if len(data) > max_size:
        raise FileSizeLimitError(
            f"Decoded binary content ({len(data)} bytes) exceeds maximum "
            f"size of {max_size} bytes"
        )

    return _atomic_write_bytes(target, data)


# ---------------------------------------------------------------------------
# Core write logic
# ---------------------------------------------------------------------------


def _write_file_results(
    target: Path,
    digest_file: FileEntry,
    exists: bool,
    *,
    overwrite: bool,
    skip_existing: bool,
    backup: bool,
    dry_run: bool,
    max_binary_size: int = 100 * 1024 * 1024,
    max_file_size: int = 500 * 1024 * 1024,
) -> list[WriteResult]:
    """Write a single file, handling conflict policies.

    Returns a list of :class:`WriteResult` objects (typically one, but two
    when ``backup`` is active — one for the backup, one for the write).
    """
    from .exceptions import FileSizeLimitError

    if digest_file.size > max_file_size:
        raise FileSizeLimitError(
            f"File {digest_file.path!r} ({digest_file.size} bytes) exceeds "
            f"maximum file size of {max_file_size} bytes"
        )

    if exists and not (overwrite or skip_existing or backup):
        raise FileExistsConflictError(digest_file.path)

    if exists and skip_existing and not overwrite and not backup:
        return [WriteResult(path=digest_file.path, action="skipped")]

    if dry_run:
        results: list[WriteResult] = []
        if exists and backup:
            results.append(WriteResult(path=digest_file.path, action="backed_up"))
        action = "would_overwrite" if exists else "would_create"
        results.append(
            WriteResult(
                path=digest_file.path, action=action, bytes_written=digest_file.size
            )
        )
        return results

    target.parent.mkdir(parents=True, exist_ok=True)
    results = []

    if exists and backup:
        backup_path = _next_backup_path(target)
        try:
            target.rename(backup_path)
        except OSError as exc:
            raise FileWriteError(
                f"Failed to back up {target} to {backup_path}: {exc}"
            ) from exc
        results.append(WriteResult(path=digest_file.path, action="backed_up"))
        exists = False

    if digest_file.is_binary:
        bytes_written = reconstruct_binary_file(
            target, digest_file.content, max_size=max_binary_size
        )
    else:
        bytes_written = _atomic_write(target, digest_file.content)

    action = "overwritten" if exists else "created"
    results.append(
        WriteResult(path=digest_file.path, action=action, bytes_written=bytes_written)
    )
    return results


# ---------------------------------------------------------------------------
# Streaming writer  — core primitive
# ---------------------------------------------------------------------------


def reconstruct_files_stream(
    entries: Iterator[FileEntry],
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    skip_existing: bool = False,
    backup: bool = False,
    dry_run: bool = False,
    max_binary_size: int = 100 * 1024 * 1024,
    max_file_size: int = 500 * 1024 * 1024,
) -> ReconstructionResult:
    """Reconstruct files from an iterable of :class:`FileEntry` objects.

    This is the core streaming primitive.  Memory usage is proportional to
    the size of the single largest file — files are written one at a time
    as they arrive from the iterator.

    Args:
        entries: Iterator yielding :class:`FileEntry` objects.
        output_dir: Directory to reconstruct into.
        overwrite: Overwrite existing files.
        skip_existing: Skip existing files.
        backup: Back up existing files before overwriting.
        dry_run: Report without writing.
        max_binary_size: Maximum decoded binary payload size (default 100 MB).
        max_file_size: Maximum file content size (default 500 MB).

    Returns:
        A :class:`ReconstructionResult`.

    Raises:
        FileExistsConflictError: If a file exists and no policy is set.
        PathTraversalError: If any path escapes ``output_dir``.
        FileWriteError: If a write fails.
    """
    out_dir = Path(output_dir)
    warnings: list[str] = []
    results: list[WriteResult] = []

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    elif not out_dir.exists():
        warnings.append(f"Output directory does not exist yet: {out_dir}")

    for digest_file in validate_entries_stream(entries):
        target = validate_safe_path(digest_file.path, out_dir)
        exists = target.exists()

        file_results = _write_file_results(
            target,
            digest_file,
            exists,
            overwrite=overwrite,
            skip_existing=skip_existing,
            backup=backup,
            dry_run=dry_run,
            max_binary_size=max_binary_size,
            max_file_size=max_file_size,
        )
        results.extend(file_results)

    return ReconstructionResult(
        output_dir=str(out_dir),
        results=tuple(results),
        dry_run=dry_run,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Convenience wrappers  (backward-compatible)
# ---------------------------------------------------------------------------


def reconstruct_files(
    summary: DigestSummary | Repository,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    skip_existing: bool = False,
    backup: bool = False,
    dry_run: bool = False,
    max_binary_size: int = 100 * 1024 * 1024,
    max_file_size: int = 500 * 1024 * 1024,
) -> ReconstructionResult:
    """Reconstruct all files from a validated digest summary onto disk.

    This is the backward-compatible API that accepts a :class:`DigestSummary`
    or :class:`Repository`.  Internally it streams file entries through the
    same writer pipeline.

    Args:
        summary: The parsed and validated digest.
        output_dir: Directory to reconstruct into.
        overwrite: Overwrite existing files.
        skip_existing: Skip existing files.
        backup: Back up to ``*.bak`` before overwriting.
        dry_run: Report without writing.
        max_binary_size: Maximum decoded binary payload (default 100 MB).
        max_file_size: Maximum file content (default 500 MB).

    Returns:
        A :class:`ReconstructionResult`.
    """
    if isinstance(summary, Repository):
        files: Iterator[FileEntry] = iter(summary.files)
    else:
        files = (
            FileEntry(
                path=f.path, content=f.content, size=f.size, line_number=f.line_number
            )
            for f in summary.files
        )

    return reconstruct_files_stream(
        files,
        output_dir,
        overwrite=overwrite,
        skip_existing=skip_existing,
        backup=backup,
        dry_run=dry_run,
        max_binary_size=max_binary_size,
        max_file_size=max_file_size,
    )


# ---------------------------------------------------------------------------
# Placeholder features (future)
# ---------------------------------------------------------------------------


def reconstruct_files_parallel(
    *_args: object, **_kwargs: object
) -> ReconstructionResult:
    raise NotImplementedFeatureError("Parallel reconstruction is not yet implemented.")


def resume_reconstruction(*_args: object, **_kwargs: object) -> ReconstructionResult:
    raise NotImplementedFeatureError("Resumable reconstruction is not yet implemented.")
