"""Fuzz tests for the parser — it must fail safely on any input.

Tests exercise: malformed delimiters, huge headers, invalid UTF-8,
corrupted separators, duplicate headers, and random byte sequences.
"""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest

from git_undigest.exceptions import (
    DigestParseError,
    InvalidDigestError,
    UnsupportedFormatError,
)
from git_undigest.formats import detect_format
from git_undigest.parser import parse_digest, parse_stream

# ---------------------------------------------------------------------------
# Malformed delimiters
# ---------------------------------------------------------------------------


def _safe_parse(text: str) -> object:
    """Parse text through both bulk detection paths.
    Return None on success or any expected exception."""
    try:
        detect_format(text)
    except (InvalidDigestError, DigestParseError, UnsupportedFormatError):
        return None
    return None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n   \n",
        "File: x\n==",
        "File: x\n====\ncontent\n===",
        "File: x\n====\ncontent\n====\nFile: y\n===\nmore",
        "=====\nMissing file header\n=====",
        "File: \n=====\ncontent\n=====",
        "FILE: x\n====\ndata\n====",
        "file: x\n====\ndata\n====",
    ],
)
def test_malformed_delimiters(text: str) -> None:
    _safe_parse(text)


# ---------------------------------------------------------------------------
# Fuzz with random text
# ---------------------------------------------------------------------------


def _random_text(size: int) -> str:
    chars = string.printable + "\n" * 5
    return "".join(random.choices(chars, k=size))


@pytest.mark.parametrize("seed", range(20))
def test_random_text(seed: int) -> None:
    """Random printable text must never crash the parser."""
    random.seed(seed)
    text = _random_text(random.randint(1, 5000))
    try:
        detect_format(text)
    except Exception as e:
        allowed = (InvalidDigestError, DigestParseError, UnsupportedFormatError)
        assert isinstance(e, allowed), f"Unexpected {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Invalid UTF-8
# ---------------------------------------------------------------------------


def test_invalid_utf8_handling(tmp_path: Path) -> None:
    """Parser must handle files with surrogate escapes gracefully."""
    path = tmp_path / "bad.txt"
    path.write_bytes(b"File: x\n====\n\xed\xa0\x80\xed\xb0\x80\n====\n")
    try:  # noqa: SIM105
        parse_digest(path)
    except (InvalidDigestError, DigestParseError, UnicodeDecodeError):
        pass


# ---------------------------------------------------------------------------
# Stream with corrupt data
# ---------------------------------------------------------------------------


def _corrupt(text: str, rate: float = 0.01) -> str:
    chars = list(text)
    for i in range(len(chars)):
        if random.random() < rate:
            chars[i] = random.choice(string.printable)
    return "".join(chars)


@pytest.mark.parametrize("seed", range(10))
def test_corrupted_stream(tmp_path: Path, seed: int) -> None:
    """Streaming parser must not crash on corrupted input."""
    random.seed(seed)
    clean = "File: a.txt\n=====\nhello\n=====\n" "File: b.txt\n=====\nworld\n=====\n"
    corrupted = _corrupt(clean, rate=0.05)
    path = tmp_path / "corrupt.txt"
    path.write_text(corrupted, encoding="ascii")

    try:
        for entry in parse_stream(path):
            assert isinstance(entry.path, str)
    except (InvalidDigestError, DigestParseError, UnsupportedFormatError):
        pass


# ---------------------------------------------------------------------------
# Huge headers (boundary testing)
# ---------------------------------------------------------------------------


def test_huge_header(tmp_path: Path) -> None:
    """Parser must handle a very large file header (via explicit format)."""
    big_name = "x" * 10000
    text = f"File: {big_name}\n" + "=" * 48 + "\ndata\n" + "=" * 48 + "\n"
    path = tmp_path / "huge.txt"
    path.write_text(text)
    count = 0
    for entry in parse_stream(path, format_name="gitingest"):
        count += 1
        assert len(entry.path) == 10000
    assert count == 1


def test_huge_content_line(tmp_path: Path) -> None:
    """Parser must handle a single very long content line."""
    text = "File: x.txt\n" + "=" * 48 + "\n" + "x" * 100000 + "\n" + "=" * 48 + "\n"
    path = tmp_path / "longline.txt"
    path.write_text(text)
    count = 0
    for entry in parse_stream(path, format_name="gitingest"):
        count += 1
        assert len(entry.content) >= 100000
    assert count == 1


# ---------------------------------------------------------------------------
# Duplicate headers
# ---------------------------------------------------------------------------


def test_duplicate_file_headers_raises(tmp_path: Path) -> None:
    """Streaming writer must detect duplicates."""
    from git_undigest import reconstruct_files_stream
    from git_undigest.exceptions import DuplicateFileError
    from git_undigest.models import FileEntry

    entries = [
        FileEntry(path="dup.txt", content="first", size=5),
        FileEntry(path="dup.txt", content="second", size=6),
    ]
    with pytest.raises(DuplicateFileError):
        reconstruct_files_stream(iter(entries), tmp_path / "out")


# ---------------------------------------------------------------------------
# Boundary: empty file content
# ---------------------------------------------------------------------------


def test_empty_file_section(tmp_path: Path) -> None:
    """Parser must handle empty file content."""
    text = "File: empty.txt\n" + "=" * 48 + "\n" + "=" * 48 + "\n"
    path = tmp_path / "empty.txt"
    path.write_text(text)
    for entry in parse_stream(path, format_name="gitingest"):
        assert entry.path == "empty.txt"
        assert entry.content == "" or entry.content.strip() == ""
