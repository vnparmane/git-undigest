"""Data models used throughout git-undigest.

These are plain dataclasses (no external dependencies required) describing
the parsed contents of a digest file, the result of reconstructing it, and
the intermediate repository model.

:class:`Repository` is the canonical internal model.  All new code should
operate on :class:`Repository` and :class:`FileEntry`.

:class:`DigestSummary` and :class:`DigestFile` remain only for backward
compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

# ---------------------------------------------------------------------------
# Canonical model — everything new should use these
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """A single file entry in a :class:`Repository`.

    Unlike the legacy :class:`DigestFile`, this is a mutable dataclass
    that can carry optional checksum and binary metadata.

    Attributes:
        path: Relative file path using forward slashes.
        content: Text content of the file. For binary files this holds
            the raw decoded content (the base64 decoding is already applied).
        size: Size in bytes (UTF-8 encoded for text, raw length for binary).
        checksum: Optional SHA-256 hex digest of the file content.
        is_binary: ``True`` if the original content was base64-encoded binary.
        line_number: Line number in the source digest where this file's
            header was found (useful for error messages).
    """

    path: str
    content: str
    size: int
    checksum: str | None = None
    is_binary: bool = False
    line_number: int = 0

    @property
    def extension(self) -> str:
        """Return the lowercase file extension, without the leading dot."""
        suffix = PurePosixPath(self.path).suffix
        return suffix.lstrip(".").lower()

    @property
    def name(self) -> str:
        """Return the final path component (file name)."""
        return PurePosixPath(self.path).name

    def to_digest_file(self) -> DigestFile:
        """Convert to a legacy :class:`DigestFile` (lossy — checksum is dropped)."""
        return DigestFile(
            path=self.path,
            content=self.content,
            size=self.size,
            line_number=self.line_number,
        )


@dataclass
class Repository:
    """A repository reconstructed from a digest.

    This is the canonical internal model that flows from the parser to the
    writer and validator.  Each :class:`FileEntry` holds one file's data
    and metadata.

    Attributes:
        name: Repository name (best-effort from the digest).
        files: List of all file entries in the repository.
    """

    name: str
    files: list[FileEntry] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def directories(self) -> set[str]:
        """Return the set of all directory paths implied by file paths."""
        dirs: set[str] = set()
        for f in self.files:
            parts = PurePosixPath(f.path).parts[:-1]
            current = PurePosixPath()
            for part in parts:
                current = current / part
                dirs.add(str(current))
        return dirs

    @classmethod
    def from_digest_summary(cls, summary: DigestSummary) -> Repository:
        """Build a :class:`Repository` from a legacy :class:`DigestSummary`.

        Args:
            summary: The parsed digest summary.

        Returns:
            A new :class:`Repository` with the same data.
        """
        return summary.to_repository()

    def to_digest_summary(self) -> DigestSummary:
        """Convert back to a legacy :class:`DigestSummary` (lossy — checksums dropped).

        Returns:
            A :class:`DigestSummary` with the same file data.
        """
        return DigestSummary(
            repo_name=self.name,
            files=tuple(f.to_digest_file() for f in self.files),
        )


# ---------------------------------------------------------------------------
# Legacy models (backward-compatible)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DigestFile:
    """Legacy: a single file entry parsed out of a digest.

    .. deprecated::
        Use :class:`FileEntry` in new code.
    """

    path: str
    content: str
    size: int
    line_number: int = 0

    @property
    def extension(self) -> str:
        """Return the lowercase file extension, without the leading dot."""
        suffix = PurePosixPath(self.path).suffix
        return suffix.lstrip(".").lower()

    @property
    def name(self) -> str:
        """Return the final path component (file name)."""
        return PurePosixPath(self.path).name


@dataclass(frozen=True, slots=True)
class DigestSummary:
    """Legacy: high level metadata about a repository digest.

    .. deprecated::
        Use :class:`Repository` in new code.
    """

    repo_name: str
    files: tuple[DigestFile, ...] = field(default_factory=tuple)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def directories(self) -> set[str]:
        """Return the set of all directory paths implied by file paths."""
        dirs: set[str] = set()
        for f in self.files:
            parts = PurePosixPath(f.path).parts[:-1]
            current = PurePosixPath()
            for part in parts:
                current = current / part
                dirs.add(str(current))
        return dirs

    def to_repository(self) -> Repository:
        """Convert this summary to a :class:`Repository` object.

        Returns:
            A :class:`Repository` with the same name and file entries.
        """
        entries = [
            FileEntry(
                path=f.path, content=f.content, size=f.size, line_number=f.line_number
            )
            for f in self.files
        ]
        return Repository(name=self.repo_name, files=entries)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Outcome of writing a single file during reconstruction.

    Attributes:
        path: Relative path of the file that was processed.
        action: One of ``"created"``, ``"overwritten"``, ``"skipped"``,
            ``"backed_up"``, or ``"would_create"`` / ``"would_overwrite"``
            for dry-run mode.
        bytes_written: Number of bytes written (0 for skipped/dry-run).
    """

    path: str
    action: str
    bytes_written: int = 0


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    """Aggregate result of a full reconstruction run.

    Attributes:
        output_dir: The output directory the repository was written to.
        results: Per-file :class:`WriteResult` entries.
        dry_run: Whether this was a dry-run (nothing actually written).
        warnings: Any non-fatal warnings collected during the run.
    """

    output_dir: str
    results: tuple[WriteResult, ...] = field(default_factory=tuple)
    dry_run: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def created(self) -> list[WriteResult]:
        return [r for r in self.results if r.action in ("created", "would_create")]

    @property
    def overwritten(self) -> list[WriteResult]:
        return [
            r for r in self.results if r.action in ("overwritten", "would_overwrite")
        ]

    @property
    def skipped(self) -> list[WriteResult]:
        return [r for r in self.results if r.action == "skipped"]

    @property
    def backed_up(self) -> list[WriteResult]:
        return [r for r in self.results if r.action == "backed_up"]

    @property
    def total_bytes_written(self) -> int:
        return sum(r.bytes_written for r in self.results)


@dataclass(frozen=True, slots=True)
class StatsResult:
    """Statistics computed over a digest.

    Attributes:
        file_count: Total number of files.
        folder_count: Total number of distinct folders.
        total_bytes: Sum of all file sizes in bytes.
        largest_file: Path of the largest file, or ``None`` if empty.
        largest_file_size: Size in bytes of the largest file.
        average_file_size: Mean file size in bytes.
        extension_counts: Mapping of extension -> count.
        estimated_tokens: Rough estimate of LLM tokens (chars / 4).
    """

    file_count: int
    folder_count: int
    total_bytes: int
    largest_file: str | None
    largest_file_size: int
    average_file_size: float
    extension_counts: dict[str, int]
    estimated_tokens: int
