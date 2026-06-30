"""Tests for git_undigest.validator, especially path-traversal security."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_undigest.exceptions import (
    DuplicateFileError,
    InvalidDigestError,
    PathTraversalError,
)
from git_undigest.models import DigestFile
from git_undigest.validator import validate_digest_files, validate_safe_path


@pytest.mark.parametrize(
    "bad_path",
    [
        "../../../etc/passwd",
        "../secret.txt",
        "../../escape.txt",
        "a/../../escape.txt",
        "/etc/shadow",
        "C:\\Windows\\System32\\evil.dll",
        "C:/Windows/System32/evil.dll",
        "\\\\server\\share\\file.txt",
        "",
        "   ",
    ],
)
def test_validate_safe_path_rejects_unsafe_paths(tmp_path: Path, bad_path: str) -> None:
    with pytest.raises(PathTraversalError):
        validate_safe_path(bad_path, tmp_path)


def test_validate_safe_path_rejects_null_byte(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        validate_safe_path("foo\x00bar.txt", tmp_path)


def test_validate_safe_path_rejects_windows_reserved_name(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        validate_safe_path("CON.txt", tmp_path)
    with pytest.raises(PathTraversalError):
        validate_safe_path("sub/dir/aux", tmp_path)


@pytest.mark.parametrize(
    "good_path",
    [
        "README.md",
        "src/main.py",
        "a/b/c/d/e.txt",
        "file.with.dots.txt",
        "unicode/résumé.txt",
        "dir/./file.txt",
    ],
)
def test_validate_safe_path_accepts_safe_paths(tmp_path: Path, good_path: str) -> None:
    result = validate_safe_path(good_path, tmp_path)
    assert result.is_absolute()
    assert tmp_path.resolve() in result.parents or result.parent == tmp_path.resolve()


def test_validate_safe_path_linux_style(tmp_path: Path) -> None:
    result = validate_safe_path("a/b/c.txt", tmp_path)
    assert result == (tmp_path.resolve() / "a" / "b" / "c.txt")


def test_validate_safe_path_windows_style_relative_with_backslash(
    tmp_path: Path,
) -> None:
    # Relative windows-style separators should be normalized, not treated
    # as absolute.
    result = validate_safe_path("a\\b\\c.txt", tmp_path)
    assert result == (tmp_path.resolve() / "a" / "b" / "c.txt")


def test_validate_digest_files_detects_duplicates() -> None:
    files = (
        DigestFile(path="a.txt", content="1", size=1),
        DigestFile(path="a.txt", content="2", size=1),
    )
    with pytest.raises(DuplicateFileError):
        validate_digest_files(files)


def test_validate_digest_files_empty_raises() -> None:
    with pytest.raises(InvalidDigestError):
        validate_digest_files(())


def test_validate_digest_files_invalid_utf8_replacement_char_raises() -> None:
    files = (DigestFile(path="a.txt", content="bad \ufffd content", size=10),)
    with pytest.raises(InvalidDigestError):
        validate_digest_files(files)


def test_validate_digest_files_accepts_valid_unique_files() -> None:
    files = (
        DigestFile(path="a.txt", content="1", size=1),
        DigestFile(path="b/c.txt", content="2", size=1),
    )
    validate_digest_files(files)  # should not raise
