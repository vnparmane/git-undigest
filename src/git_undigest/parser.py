"""Top-level digest parsing entry points.

This module is deliberately thin: it reads digest text from disk (or
accepts it directly), picks the right format plugin via
:mod:`git_undigest.formats`, and delegates parsing to it. It performs no
validation and no writing -- see :mod:`git_undigest.validator` and
:mod:`git_undigest.writer` respectively.

Streaming support
-----------------
Use :func:`parse_stream` or :func:`iter_files` for constant-memory
processing of large digests. They yield :class:`FileEntry` objects one at
a time without loading the entire digest into memory.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import IO

from .exceptions import InvalidDigestError
from .formats import DigestFormat, detect_format, get_format
from .models import DigestSummary, FileEntry

# Maximum bytes to read from the beginning of a file for format detection.
_SNIFF_SIZE = 8192


# ---------------------------------------------------------------------------
# Compression helpers
# ---------------------------------------------------------------------------


def _get_compression_suffix(path: Path) -> str:
    """Return the compression suffix (``.gz``, ``.xz``, ``.zst``) or ``""``."""
    known = {".gz", ".xz", ".zst"}
    for s in reversed(path.suffixes):
        if s.lower() in known:
            return s.lower()
    return ""


def _open_maybe_compressed(path: Path) -> IO[str]:
    """Open *path* for UTF-8 text reading, auto-detecting compression.

    Supports ``.gz`` (gzip), ``.xz`` (lzma), and ``.zst`` (zstandard)
    transparently. Falls back to plain ``open()`` for uncompressed files.

    Args:
        path: Path to the digest file.

    Returns:
        An open text stream.

    Raises:
        InvalidDigestError: If the file cannot be opened or decoded.
    """
    comp = _get_compression_suffix(path)
    try:
        if comp == ".gz":
            import gzip

            return gzip.open(path, "rt", encoding="utf-8")
        elif comp == ".xz":
            import lzma

            return lzma.open(path, "rt", encoding="utf-8")
        elif comp == ".zst":
            return _open_zst(path)
        else:
            return open(path, encoding="utf-8")
    except FileNotFoundError:
        raise InvalidDigestError(f"Digest file not found: {path}") from None
    except IsADirectoryError:
        raise InvalidDigestError(
            f"Expected a digest file, got a directory: {path}"
        ) from None
    except (UnicodeDecodeError, LookupError) as exc:
        raise InvalidDigestError(
            f"Digest file is not valid UTF-8: {path} ({exc})"
        ) from exc


def _open_zst(path: Path) -> IO[str]:
    """Open a zstandard-compressed file for UTF-8 text reading.

    Raises:
        InvalidDigestError: If ``zstandard`` is not installed.
    """
    try:
        import zstandard  # type: ignore[import-not-found]
    except ImportError as exc:
        raise InvalidDigestError(
            f"Cannot open {path}: the 'zstandard' package is required for .zst files. "
            "Install it with: pip install git-undigest[zstd]"
        ) from exc

    fh = zstandard.open(path, "rt", encoding="utf-8")
    return fh  # type: ignore[no-any-return]


def _validate_digest_path(path: Path) -> None:
    """Validate that *path* exists, is not a directory, and is readable.

    Raises:
        InvalidDigestError: If any check fails.
    """
    if not path.exists():
        raise InvalidDigestError(f"Digest file not found: {path}")
    if path.is_dir():
        raise InvalidDigestError(f"Expected a digest file, got a directory: {path}")


# ---------------------------------------------------------------------------
# Bulk-read API
# ---------------------------------------------------------------------------


def read_digest_text(digest_path: str | Path) -> str:
    """Read a digest file from disk as UTF-8 text.

    Supports compressed files (``.gz``, ``.xz``, ``.zst``).

    Args:
        digest_path: Path to the digest file.

    Returns:
        The full decoded text content.

    Raises:
        InvalidDigestError: If the file does not exist, is a directory, or
            cannot be decoded as UTF-8.
    """
    with _open_maybe_compressed(Path(digest_path)) as fh:
        return fh.read()


def parse_compressed_digest(
    digest_path: str | Path, *, format_name: str | None = None
) -> DigestSummary:
    """Parse a compressed digest file (``.gz``, ``.xz``, or ``.zst``).

    Compression is auto-detected from the file extension. This function
    is a convenience alias for :func:`parse_digest`.

    Args:
        digest_path: Path to the compressed digest file.
        format_name: Optional explicit digest format name.

    Returns:
        The parsed :class:`DigestSummary`.
    """
    return parse_digest(digest_path, format_name=format_name)


def parse_digest(
    digest_path: str | Path, *, format_name: str | None = None
) -> DigestSummary:
    """Parse a digest file from disk into a :class:`DigestSummary`.

    Supports compressed digests automatically.

    Args:
        digest_path: Path to the digest file on disk.
        format_name: Optional explicit format name (e.g. ``"gitingest"``).
            If omitted, the format is auto-detected.

    Returns:
        The parsed :class:`DigestSummary`.

    Raises:
        InvalidDigestError: If the digest is empty, unreadable, or has no
            recognizable file sections.
        UnsupportedFormatError: If ``format_name`` is omitted and no
            registered format recognizes the content.
        DigestParseError: If the content matches a format but contains a
            malformed section.
    """
    text = read_digest_text(digest_path)
    return parse_digest_text(text, format_name=format_name)


def parse_digest_text(text: str, *, format_name: str | None = None) -> DigestSummary:
    """Parse raw digest text (already in memory) into a :class:`DigestSummary`.

    Args:
        text: Raw digest text.
        format_name: Optional explicit format name. If omitted, the format
            is auto-detected from the text content.

    Returns:
        The parsed :class:`DigestSummary`.

    Raises:
        InvalidDigestError: If the digest text is empty or has no
            recognizable file sections.
        UnsupportedFormatError: If no registered format matches.
        DigestParseError: If a matched format finds a malformed section.
    """
    if not text or not text.strip():
        raise InvalidDigestError("Digest is empty.")
    fmt = get_format(format_name) if format_name else detect_format(text)
    return fmt.parse(text)


# ---------------------------------------------------------------------------
# Streaming API  — truly streaming, never loads the full file
# ---------------------------------------------------------------------------


def _detect_format_from_path(
    path: Path,
) -> tuple[DigestFormat, str]:
    """Open *path*, read a small prefix, detect the format, and return both.

    Returns ``(fmt, prefix)`` where *prefix* is the text read so callers
    can restore stream position when reopening is not an option.

    The file is opened and closed once for sniffing.
    """
    with _open_maybe_compressed(path) as fh:
        prefix = fh.read(_SNIFF_SIZE)
    if not prefix:
        raise InvalidDigestError("Digest is empty (zero bytes read).")
    fmt = detect_format(prefix)
    return fmt, prefix


def parse_stream(
    digest_path: str | Path,
    *,
    format_name: str | None = None,
) -> Iterator[FileEntry]:
    """Parse a digest file as a stream of :class:`FileEntry` objects.

    Unlike :func:`parse_digest`, this function yields files one at a time
    and does not load the entire digest into memory. Memory usage is
    proportional to the size of the largest single file in the digest.

    The file is opened twice: once to read a small prefix for format
    detection, then again for line-by-line streaming.  This keeps the
    streaming path truly streaming — no ``peek`` + ``StringIO`` pattern.

    Supports compressed digests (``.gz``, ``.xz``, ``.zst``) automatically.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit format name. Auto-detected if omitted.

    Yields:
        :class:`FileEntry` for each file in the digest.

    Raises:
        InvalidDigestError: If the digest file is missing or empty.
        UnsupportedFormatError: If no registered format matches.
        DigestParseError: If a section is malformed.
    """
    path = Path(digest_path)
    _validate_digest_path(path)

    if format_name:
        fmt = get_format(format_name)
    else:
        fmt, _ = _detect_format_from_path(path)

    with _open_maybe_compressed(path) as stream:
        yield from fmt.parse_stream(stream)


def iter_files(
    digest_path: str | Path,
    *,
    format_name: str | None = None,
) -> Iterator[str]:
    """Iterate over file paths in a digest without loading file contents.

    This is a lightweight alternative to :func:`list_files` that streams
    just the paths, useful for very large digests when you only need the
    file listing.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit format name.

    Yields:
        File path strings as they are encountered.
    """
    for entry in parse_stream(digest_path, format_name=format_name):
        yield entry.path
