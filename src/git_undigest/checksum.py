"""Checksum utilities.

Provides SHA-256 hashing helpers used for integrity verification. Full
digest-embedded checksum verification is a designed-but-not-yet-implemented
feature (see :func:`verify_checksum`), since the GitIngest format itself
does not currently embed per-file checksums.
"""

from __future__ import annotations

import hashlib

from .exceptions import ChecksumMismatchError, NotImplementedFeatureError


def sha256_text(content: str) -> str:
    """Compute the SHA-256 hex digest of a text string (UTF-8 encoded).

    Args:
        content: The text content to hash.

    Returns:
        The hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hex digest of raw bytes.

    Args:
        data: The raw bytes to hash.

    Returns:
        The hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(data).hexdigest()


def verify_checksum(path: str, content: str, expected_checksum: str) -> None:
    """Verify file content against an expected SHA-256 checksum.

    This is a placeholder for future digest formats that embed per-file
    checksums. The current GitIngest text format has no such field, so
    callers should not invoke this unless they have an external checksum
    manifest.

    Args:
        path: The file path, used for error reporting.
        content: The file's text content.
        expected_checksum: The expected SHA-256 hex digest.

    Raises:
        ChecksumMismatchError: If the computed checksum does not match.
    """
    actual = sha256_text(content)
    if actual != expected_checksum:
        raise ChecksumMismatchError(path, expected_checksum, actual)


def verify_checksum_manifest(*_args: object, **_kwargs: object) -> None:
    """Verify an entire reconstruction against a SHA-256 checksum manifest.

    Designed interface for a future feature where a digest is accompanied
    by a manifest file mapping paths to expected checksums.

    Raises:
        NotImplementedFeatureError: Always, until implemented.
    """
    raise NotImplementedFeatureError(
        "Checksum manifest verification is not yet implemented."
    )
