"""Validation logic for parsed digests and individual file paths.

This module is the single source of truth for "is this safe / well-formed"
checks. Neither the parser nor the writer should duplicate this logic;
they call into here instead.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from .exceptions import (
    DuplicateFileError,
    InvalidDigestError,
    PathTraversalError,
)
from .models import DigestFile, DigestSummary, FileEntry

# Windows reserved device names (case-insensitive), with or without an
# extension, e.g. "CON", "con.txt", "LPT1".
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_WINDOWS_DRIVE_RE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def is_absolute_or_drive_path(path: str) -> bool:
    """Detect POSIX-absolute, Windows-absolute, Windows-drive, or UNC paths.

    Args:
        path: The raw path string from a digest entry.

    Returns:
        True if the path is absolute by any platform's convention.
    """
    if not path:
        return False
    if path.startswith("/") or path.startswith("\\"):
        return True
    # Windows drive letter, e.g. "C:\..." or "C:/..."
    if len(path) >= 2 and path[0] in _WINDOWS_DRIVE_RE_CHARS and path[1] == ":":
        return True
    # UNC path, e.g. "\\server\share"
    return bool(path.startswith("\\\\"))


def has_windows_reserved_component(path: str) -> bool:
    """Check whether any path component is a Windows reserved device name."""
    normalized = path.replace("\\", "/")
    for part in normalized.split("/"):
        stem = part.split(".")[0].lower()
        if stem in _WINDOWS_RESERVED:
            return True
    return False


def validate_safe_path(raw_path: str, output_dir: Path) -> Path:
    """Validate and resolve a digest file path against an output directory.

    This is the core security boundary of the package: it guarantees the
    returned path is a descendant of ``output_dir`` after full resolution,
    rejecting any form of path traversal, absolute paths, drive letters,
    UNC paths, or null bytes.

    Args:
        raw_path: The path as it appeared in the digest (may use either
            slash style).
        output_dir: The target output directory, treated as the sandbox
            root.

    Returns:
        The resolved, absolute :class:`~pathlib.Path` the file should be
        written to.

    Raises:
        PathTraversalError: If the path is empty, absolute, contains a
            drive letter / UNC prefix, contains a null byte, uses a
            Windows-reserved device name, or resolves outside of
            ``output_dir``.
    """
    validate_path_string_safety(raw_path)

    normalized = raw_path.replace("\\", "/")
    collapsed = posixpath.normpath(normalized)

    # Belt-and-braces: resolve against the real output directory and
    # confirm containment, in case of platform-specific quirks (e.g.
    # symlinked output_dir, case-insensitive filesystems).
    output_root = output_dir.resolve()
    candidate = (output_root / collapsed).resolve()

    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise PathTraversalError(
            raw_path, "resolved path escapes output directory"
        ) from exc

    return candidate


def validate_path_string_safety(raw_path: str) -> None:
    """Validate a path string's safety without resolving it against any
    real output directory.

    This is the subset of :func:`validate_safe_path`'s checks that can be
    performed purely on the string itself: absolute paths, drive letters,
    UNC paths, null bytes, reserved device names, and ``..`` segments that
    would escape a relative root. It is used by
    :func:`validate_digest_files` so that ``validate()`` (which has no
    output directory) still catches unsafe paths early.

    Args:
        raw_path: The path as it appeared in the digest.

    Raises:
        PathTraversalError: If the path is unsafe by any of the above
            criteria.
    """
    if raw_path is None or raw_path.strip() == "":
        raise PathTraversalError(raw_path or "", "empty path")

    if "\x00" in raw_path:
        raise PathTraversalError(raw_path, "null byte in path")

    if is_absolute_or_drive_path(raw_path):
        raise PathTraversalError(raw_path, "absolute or drive-qualified path")

    if has_windows_reserved_component(raw_path):
        raise PathTraversalError(raw_path, "Windows reserved device name")

    normalized = raw_path.replace("\\", "/")
    collapsed = posixpath.normpath(normalized)

    if collapsed in (".", ""):
        raise PathTraversalError(raw_path, "path resolves to the root itself")

    if collapsed.startswith("../") or collapsed == ".." or "/../" in f"/{collapsed}/":
        raise PathTraversalError(raw_path, "attempts to escape output directory")


def validate_digest_files(files: tuple[DigestFile, ...]) -> None:
    """Validate structural correctness of a list of parsed digest files.

    Checks for duplicate paths, empty paths, and invalid UTF-8 surrogate
    artifacts left over from decoding.

    Args:
        files: Parsed digest file entries.

    Raises:
        InvalidDigestError: If ``files`` is empty.
        DuplicateFileError: If the same normalized path appears twice.
        PathTraversalError: If any path is empty.
    """
    if not files:
        raise InvalidDigestError("Digest contains no files to reconstruct.")

    seen: set[str] = set()
    for f in files:
        if not f.path or not f.path.strip():
            raise PathTraversalError(f.path or "", "empty filename")

        validate_path_string_safety(f.path)

        normalized = PurePosixPath(f.path.replace("\\", "/")).as_posix()
        if normalized in seen:
            raise DuplicateFileError(f.path)
        seen.add(normalized)

        if "\ufffd" in f.content:
            # Replacement character indicates content that could not be
            # cleanly decoded as UTF-8 upstream.
            raise InvalidDigestError(
                f"File {f.path!r} contains invalid UTF-8 (replacement "
                "characters detected)."
            )


def validate_summary(summary: DigestSummary) -> None:
    """Run all structural validations against a parsed digest summary.

    Args:
        summary: The parsed digest.

    Raises:
        InvalidDigestError: If the digest has no files.
        DuplicateFileError: If duplicate file paths are present.
        PathTraversalError: If any path is empty or unsafe at the
            structural level (full output-directory containment is
            checked separately by :func:`validate_safe_path` at write
            time).
    """
    validate_digest_files(summary.files)


# ---------------------------------------------------------------------------
# Streaming validation
# ---------------------------------------------------------------------------


def validate_entries_stream(
    entries: Iterator[FileEntry],
) -> Iterator[FileEntry]:
    """Validate a stream of :class:`FileEntry` objects.

    Yields each entry after validating its path for safety and detecting
    duplicates.  Memory usage is O(number of distinct file paths), not
    O(total digest size).

    Args:
        entries: An iterator of file entries (e.g. from
            :func:`git_undigest.parser.parse_stream`).

    Yields:
        Validated :class:`FileEntry` objects.

    Raises:
        DuplicateFileError: If the same normalized path appears twice.
        PathTraversalError: If any path is empty or unsafe.
        InvalidDigestError: If the stream is empty (no files).
    """
    seen: set[str] = set()
    first = True
    for entry in entries:
        if first:
            first = False
        validate_path_string_safety(entry.path)
        normalized = PurePosixPath(entry.path.replace("\\", "/")).as_posix()
        if normalized in seen:
            raise DuplicateFileError(entry.path)
        seen.add(normalized)
        yield entry

    if first:
        raise InvalidDigestError("Digest contains no files to reconstruct.")
