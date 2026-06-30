"""Tests for git_undigest.parser and the gitingest format."""

from __future__ import annotations

import pytest

from git_undigest.exceptions import DigestParseError, InvalidDigestError
from git_undigest.parser import parse_digest_text


def test_parse_simple_digest(simple_digest: str) -> None:
    summary = parse_digest_text(simple_digest)
    assert summary.file_count == 1
    f = summary.files[0]
    assert f.path == "README.md"
    assert f.content == "# Hello\n\nWorld.\n"


def test_parse_nested_digest(nested_digest: str) -> None:
    summary = parse_digest_text(nested_digest)
    assert summary.file_count == 2
    paths = sorted(f.path for f in summary.files)
    assert paths == ["README.md", "src/nested/deep.py"]
    assert summary.repo_name == "myrepo"


def test_parse_empty_digest_raises() -> None:
    with pytest.raises(InvalidDigestError):
        parse_digest_text("")


def test_parse_digest_with_no_file_sections_raises() -> None:
    from git_undigest.exceptions import UnsupportedFormatError

    with pytest.raises((InvalidDigestError, UnsupportedFormatError)):
        parse_digest_text("just some random text\nwith no headers at all\n")


def test_parse_empty_filename_raises() -> None:
    digest = (
        "================================================\n"
        "File: \n"
        "================================================\n"
        "content\n"
    )
    with pytest.raises(DigestParseError):
        parse_digest_text(digest)


def test_parse_malformed_missing_closing_separator() -> None:
    digest = (
        "================================================\n"
        "File: a.txt\n"
        "no closing separator here\n"
        "content\n"
    )
    with pytest.raises(DigestParseError):
        parse_digest_text(digest)


def test_parse_empty_file_content() -> None:
    digest = (
        "================================================\n"
        "File: empty.txt\n"
        "================================================\n"
        "================================================\n"
        "File: next.txt\n"
        "================================================\n"
        "data\n"
    )
    summary = parse_digest_text(digest)
    assert summary.file_count == 2
    empty = next(f for f in summary.files if f.path == "empty.txt")
    assert empty.content == ""


def test_parse_unicode_filenames_and_content() -> None:
    digest = (
        "================================================\n"
        "File: 文档/résumé.txt\n"
        "================================================\n"
        "héllo wörld 你好\n"
    )
    summary = parse_digest_text(digest)
    assert summary.files[0].path == "文档/résumé.txt"
    assert "你好" in summary.files[0].content


def test_parse_windows_style_path_normalized_to_posix() -> None:
    digest = (
        "================================================\n"
        "File: src\\main.py\n"
        "================================================\n"
        "print(1)\n"
    )
    summary = parse_digest_text(digest)
    assert summary.files[0].path == "src/main.py"


def test_parse_multiple_files_in_same_directory() -> None:
    digest = (
        "================================================\n"
        "File: a.py\n"
        "================================================\n"
        "a = 1\n"
        "================================================\n"
        "File: b.py\n"
        "================================================\n"
        "b = 2\n"
        "================================================\n"
        "File: c.py\n"
        "================================================\n"
        "c = 3\n"
    )
    summary = parse_digest_text(digest)
    assert summary.file_count == 3
    assert sorted(f.path for f in summary.files) == ["a.py", "b.py", "c.py"]
