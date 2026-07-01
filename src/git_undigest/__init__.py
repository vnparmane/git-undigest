"""git-undigest: reconstruct a full repository from a GitIngest-style digest.

Public API:
    reconstruct: Parse a digest and write the resulting files to disk.
    validate: Validate a digest without writing anything.
    inspect: Produce a human-oriented summary of a digest's contents.
    stats: Produce numeric statistics about a digest.
    list_files: List every file path contained in a digest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import utils
from .exceptions import (
    BinaryDecodeError,
    ChecksumMismatchError,
    DigestIntegrityError,
    DigestParseError,
    DuplicateFileError,
    FileExistsConflictError,
    FileSizeLimitError,
    FileWriteError,
    GitUndigestError,
    InvalidDigestError,
    NotImplementedFeatureError,
    PathTraversalError,
    UnsupportedFormatError,
)
from .models import (
    DigestFile,
    DigestSummary,
    FileEntry,
    ReconstructionResult,
    Repository,
    StatsResult,
    WriteResult,
)
from .parser import iter_files, parse_digest, parse_digest_text, parse_stream
from .validator import validate_summary
from .writer import reconstruct_files, reconstruct_files_stream

__version__ = "0.2.1"

__all__ = [
    "reconstruct",
    "validate",
    "inspect",
    "stats",
    "list_files",
    "parse_digest",
    "parse_digest_text",
    "parse_stream",
    "iter_files",
    "reconstruct_files",
    "reconstruct_files_stream",
    "__version__",
    # Models
    "DigestFile",
    "DigestSummary",
    "FileEntry",
    "ReconstructionResult",
    "Repository",
    "StatsResult",
    "WriteResult",
    # Exceptions
    "GitUndigestError",
    "DigestParseError",
    "InvalidDigestError",
    "PathTraversalError",
    "DuplicateFileError",
    "ChecksumMismatchError",
    "FileWriteError",
    "FileExistsConflictError",
    "FileSizeLimitError",
    "BinaryDecodeError",
    "DigestIntegrityError",
    "UnsupportedFormatError",
    "NotImplementedFeatureError",
]


def reconstruct(
    digest_path: str | Path,
    output: str | Path = "output",
    *,
    overwrite: bool = False,
    skip_existing: bool = False,
    backup: bool = False,
    dry_run: bool = False,
    format_name: str | None = None,
) -> ReconstructionResult:
    """Reconstruct a full repository from a digest file.

    Uses streaming internally — the digest is parsed and written
    line-by-line without loading the entire file into memory.

    Args:
        digest_path: Path to the GitIngest-style digest file.
        output: Directory to reconstruct the repository into.
        overwrite: Overwrite existing files instead of erroring.
        skip_existing: Skip existing files instead of erroring.
        backup: Back up existing files to ``*.bak`` before overwriting.
        dry_run: Report what would happen without writing anything.
        format_name: Optional explicit digest format name. Auto-detected
            if omitted.

    Returns:
        A :class:`ReconstructionResult` describing what was written (or
        would be written, in dry-run mode).

    Raises:
        InvalidDigestError: If the digest is empty, unreadable, or
            structurally invalid.
        DigestParseError: If the digest format is recognized but a section
            is malformed.
        DuplicateFileError: If the digest contains duplicate file paths.
        PathTraversalError: If any file path is unsafe.
        FileExistsConflictError: If a target file exists and no overwrite
            policy was given.
        FileWriteError: If a filesystem operation fails.

    Example:
        >>> from git_undigest import reconstruct
        >>> result = reconstruct("digest.txt", output="repo")
        >>> result.output_dir
        'repo'
    """
    entries = parse_stream(digest_path, format_name=format_name)
    return reconstruct_files_stream(
        entries,
        output,
        overwrite=overwrite,
        skip_existing=skip_existing,
        backup=backup,
        dry_run=dry_run,
    )


def validate(
    digest_path: str | Path, *, format_name: str | None = None
) -> DigestSummary:
    """Validate a digest file without writing anything to disk.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit digest format name.

    Returns:
        The parsed and validated :class:`DigestSummary`, if valid.

    Raises:
        InvalidDigestError: If the digest is empty or structurally invalid.
        DigestParseError: If a section is malformed.
        DuplicateFileError: If duplicate file paths are present.
        PathTraversalError: If any file path is empty or unsafe.
    """
    summary = parse_digest(digest_path, format_name=format_name)
    validate_summary(summary)
    return summary


def inspect(
    digest_path: str | Path, *, format_name: str | None = None
) -> dict[str, Any]:
    """Produce a human-oriented summary of a digest's contents.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit digest format name.

    Returns:
        A dictionary with keys ``repo_name``, ``file_count``,
        ``languages`` (dict of language -> file count), ``largest_files``
        (list of ``(path, size)`` tuples, largest first, top 10), and
        ``tree`` (a rendered directory tree string).
    """
    summary = validate(digest_path, format_name=format_name)

    languages: dict[str, int] = {}
    for f in summary.files:
        lang = utils.detect_language(f.extension)
        if lang:
            languages[lang] = languages.get(lang, 0) + 1

    largest = sorted(summary.files, key=lambda f: f.size, reverse=True)[:10]

    return {
        "repo_name": summary.repo_name,
        "file_count": summary.file_count,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "largest_files": [(f.path, f.size) for f in largest],
        "tree": render_tree(summary),
    }


def stats(digest_path: str | Path, *, format_name: str | None = None) -> StatsResult:
    """Compute numeric statistics about a digest.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit digest format name.

    Returns:
        A populated :class:`StatsResult`.
    """
    summary = validate(digest_path, format_name=format_name)

    ext_counts: dict[str, int] = {}
    for f in summary.files:
        key = f.extension or "(no extension)"
        ext_counts[key] = ext_counts.get(key, 0) + 1

    total_chars = sum(len(f.content) for f in summary.files)

    if summary.files:
        largest = max(summary.files, key=lambda f: f.size)
        largest_path: str | None = largest.path
        largest_size = largest.size
    else:
        largest_path = None
        largest_size = 0

    file_count = summary.file_count
    avg = (summary.total_bytes / file_count) if file_count else 0.0

    return StatsResult(
        file_count=file_count,
        folder_count=len(summary.directories),
        total_bytes=summary.total_bytes,
        largest_file=largest_path,
        largest_file_size=largest_size,
        average_file_size=avg,
        extension_counts=dict(sorted(ext_counts.items(), key=lambda kv: -kv[1])),
        estimated_tokens=utils.estimate_tokens(total_chars),
    )


def list_files(digest_path: str | Path, *, format_name: str | None = None) -> list[str]:
    """List every file path contained in a digest.

    Args:
        digest_path: Path to the digest file.
        format_name: Optional explicit digest format name.

    Returns:
        A sorted list of file paths.
    """
    summary = validate(digest_path, format_name=format_name)
    return sorted(f.path for f in summary.files)


def render_tree(summary: DigestSummary) -> str:
    """Render a directory tree string for a digest summary.

    Args:
        summary: The parsed digest.

    Returns:
        A multi-line string depicting the directory/file hierarchy.
    """
    root: dict[str, dict[str, Any] | None] = {}
    for f in summary.files:
        parts = f.path.split("/")
        node = root
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                existing = {}
                node[part] = existing
            node = existing
        node[parts[-1]] = None

    lines = [f"{summary.repo_name}/"]

    def _walk(node: dict[str, dict[str, Any] | None], prefix: str) -> None:
        entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0]))
        for idx, (name, child) in enumerate(entries):
            is_last = idx == len(entries) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if isinstance(child, dict) else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")
            if isinstance(child, dict):
                extension = "    " if is_last else "│   "
                _walk(child, prefix + extension)

    _walk(root, "")
    return "\n".join(lines)
