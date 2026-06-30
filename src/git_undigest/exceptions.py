"""Custom exception hierarchy for git-undigest.

All exceptions raised by this package derive from :class:`GitUndigestError`,
allowing callers to catch the entire family with a single ``except`` clause
while still being able to discriminate on specific failure modes.
"""

from __future__ import annotations


class GitUndigestError(Exception):
    """Base class for all git-undigest exceptions."""


class DigestParseError(GitUndigestError):
    """Raised when a digest file cannot be parsed.

    Attributes:
        line_number: The 1-indexed line number where the error occurred,
            if known.
    """

    def __init__(self, message: str, line_number: int | None = None) -> None:
        self.line_number = line_number
        if line_number is not None:
            message = f"{message} (line {line_number})"
        super().__init__(message)


class InvalidDigestError(GitUndigestError):
    """Raised when the digest is structurally invalid.

    This covers cases such as an empty digest, a digest with no recognizable
    file sections, or a digest that fails overall structural validation.
    """


class PathTraversalError(GitUndigestError):
    """Raised when a file path in the digest attempts to escape the output
    directory, or contains an absolute or otherwise unsafe path.
    """

    def __init__(self, path: str, reason: str = "path traversal detected") -> None:
        self.path = path
        super().__init__(f"Unsafe path rejected: {path!r} ({reason})")


class DuplicateFileError(GitUndigestError):
    """Raised when the same file path appears more than once in a digest."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Duplicate file path in digest: {path!r}")


class ChecksumMismatchError(GitUndigestError):
    """Raised when a file's computed checksum does not match the expected
    checksum recorded in (or alongside) the digest.
    """

    def __init__(self, path: str, expected: str, actual: str) -> None:
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checksum mismatch for {path!r}: expected {expected}, got {actual}"
        )


class FileWriteError(GitUndigestError):
    """Raised when a file cannot be written to disk."""


class FileExistsConflictError(GitUndigestError):
    """Raised when a target file already exists and no overwrite policy
    permits overwriting or skipping it.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"File already exists and no overwrite policy applies: {path!r}"
        )


class UnsupportedFormatError(GitUndigestError):
    """Raised when no registered format parser can handle a digest."""


class NotImplementedFeatureError(GitUndigestError):
    """Raised by placeholder interfaces for features that are designed but
    not yet implemented (e.g. compressed digests, parallel reconstruction).
    """


class FileSizeLimitError(GitUndigestError):
    """Raised when a file's content exceeds the configured maximum size."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BinaryDecodeError(GitUndigestError):
    """Raised when a binary payload cannot be decoded (invalid base64)."""

    def __init__(self, message: str = "Invalid binary content") -> None:
        super().__init__(message)


class DigestIntegrityError(GitUndigestError):
    """Raised when a digest fails integrity checks."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
