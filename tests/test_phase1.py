"""Tests for Phase 1: streaming, compression, binary, plugins, Repository."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from git_undigest import (
    FileEntry,
    Repository,
    parse_digest_text,
    parse_stream,
    reconstruct_files,
    reconstruct_files_stream,
)
from git_undigest.exceptions import (
    BinaryDecodeError,
    FileSizeLimitError,
    InvalidDigestError,
)

# ---------------------------------------------------------------------------
# Repository model
# ---------------------------------------------------------------------------


def test_repository_from_entries() -> None:
    repo = Repository(
        name="test-repo",
        files=[
            FileEntry(path="a.txt", content="hello", size=5),
            FileEntry(path="b.txt", content="world", size=5),
        ],
    )
    assert repo.name == "test-repo"
    assert repo.file_count == 2
    assert repo.total_bytes == 10


def test_repository_file_entry_properties() -> None:
    entry = FileEntry(path="src/main.py", content="print('x')", size=9)
    assert entry.extension == "py"
    assert entry.name == "main.py"


def test_repository_binary_flag() -> None:
    entry = FileEntry(path="img.png", content="", size=0, is_binary=True)
    assert entry.is_binary


def test_repository_checksum() -> None:
    entry = FileEntry(
        path="f.txt",
        content="data",
        size=4,
        checksum="abc123",
    )
    assert entry.checksum == "abc123"


# ---------------------------------------------------------------------------
# Streaming parser — requires file path
# ---------------------------------------------------------------------------


SAMPLE_DIGEST = """File: README.md
================================================================================
# Hello
================================================================================
File: src/main.py
================================================================================
print("hello")
================================================================================
"""


def test_parse_stream_yields_file_entries(tmp_path: Path) -> None:
    path = tmp_path / "d.txt"
    path.write_text(SAMPLE_DIGEST)
    entries = list(parse_stream(path))
    assert len(entries) == 2
    assert entries[0].path == "README.md"
    assert entries[0].content.strip() == "# Hello"
    assert entries[1].path == "src/main.py"
    assert entries[1].content.strip() == 'print("hello")'


def test_parse_stream_empty_digest_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("")
    with pytest.raises(InvalidDigestError):
        list(parse_stream(path))


def test_parse_stream_no_file_sections_raises(tmp_path: Path) -> None:
    path = tmp_path / "d.txt"
    # Text that matches gitingest sniff but has no file sections
    path.write_text("Directory structure:\n-- repo/\n", encoding="utf-8")
    with pytest.raises(InvalidDigestError):
        list(parse_stream(path, format_name="gitingest"))


def test_parse_stream_matches_parse_digest_text(tmp_path: Path) -> None:
    path = tmp_path / "d.txt"
    path.write_text(SAMPLE_DIGEST)
    summary = parse_digest_text(SAMPLE_DIGEST)
    entries = list(parse_stream(path))
    assert len(entries) == summary.file_count
    for entry, df in zip(entries, summary.files, strict=True):
        assert entry.path == df.path
        assert entry.content == df.content


# ---------------------------------------------------------------------------
# Streaming writer
# ---------------------------------------------------------------------------


def test_reconstruct_files_stream(tmp_path: Path) -> None:
    out = tmp_path / "out"
    files = [
        FileEntry(path="a.txt", content="aaa", size=3),
        FileEntry(path="sub/b.txt", content="bbb", size=3),
    ]
    result = reconstruct_files_stream(iter(files), out)
    assert (out / "a.txt").read_text() == "aaa"
    assert (out / "sub/b.txt").read_text() == "bbb"
    assert result.created[0].path == "a.txt"


def test_reconstruct_files_stream_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    files = [FileEntry(path="a.txt", content="new", size=3)]
    result = reconstruct_files_stream(iter(files), out, overwrite=True)
    assert (out / "a.txt").read_text() == "new"
    assert result.overwritten[0].path == "a.txt"


def test_reconstruct_files_stream_skip_existing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    files = [FileEntry(path="a.txt", content="new", size=3)]
    result = reconstruct_files_stream(iter(files), out, skip_existing=True)
    assert (out / "a.txt").read_text() == "old"
    assert result.skipped[0].path == "a.txt"


def test_reconstruct_files_stream_dry_run(tmp_path: Path) -> None:
    out = tmp_path / "out"
    files = [FileEntry(path="a.txt", content="data", size=4)]
    result = reconstruct_files_stream(iter(files), out, dry_run=True)
    assert not out.exists()
    assert len(result.created) == 1


def test_reconstruct_files_stream_backup(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("original")
    files = [FileEntry(path="a.txt", content="modified", size=8)]
    result = reconstruct_files_stream(iter(files), out, backup=True)
    assert (out / "a.txt").read_text() == "modified"
    assert (out / "a.txt.bak").read_text() == "original"
    assert len(result.backed_up) == 1
    assert len(result.created) == 1


def test_reconstruct_files_with_repository(tmp_path: Path) -> None:
    out = tmp_path / "out"
    repo = Repository(
        name="test",
        files=[FileEntry(path="f.txt", content="data", size=4)],
    )
    result = reconstruct_files(repo, out)
    assert (out / "f.txt").read_text() == "data"
    assert len(result.created) == 1


# ---------------------------------------------------------------------------
# Binary file support
# ---------------------------------------------------------------------------


def test_binary_file_reconstruction(tmp_path: Path) -> None:
    from git_undigest.writer import reconstruct_binary_file

    payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    b64 = base64.b64encode(payload).decode("ascii")
    target = tmp_path / "test.png"
    written = reconstruct_binary_file(target, b64)
    assert written == len(payload)
    assert target.read_bytes() == payload


def test_binary_decode_invalid_base64() -> None:
    from git_undigest.writer import reconstruct_binary_file

    with pytest.raises(BinaryDecodeError):
        reconstruct_binary_file(Path("out.bin"), "!!!invalid base64!!!")


def test_binary_decode_empty_content(tmp_path: Path) -> None:
    from git_undigest.writer import reconstruct_binary_file

    target = tmp_path / "empty.bin"
    written = reconstruct_binary_file(target, "")
    assert written == 0
    assert target.read_bytes() == b""


# ---------------------------------------------------------------------------
# Security hardening — file size limits
# ---------------------------------------------------------------------------


def test_writer_file_size_limit(tmp_path: Path) -> None:
    with pytest.raises(FileSizeLimitError):
        reconstruct_files_stream(
            iter([FileEntry(path="big.txt", content="x" * 1000, size=1000)]),
            tmp_path / "out",
            max_file_size=100,
        )


def test_writer_binary_size_limit(tmp_path: Path) -> None:
    from git_undigest.writer import reconstruct_binary_file

    large_payload = b"x" * 200
    b64 = base64.b64encode(large_payload).decode("ascii")
    with pytest.raises(FileSizeLimitError):
        reconstruct_binary_file(tmp_path / "big.bin", b64, max_size=100)


# ---------------------------------------------------------------------------
# Plugin system
# ---------------------------------------------------------------------------


def _cleanup_test_format(name: str = "test") -> None:
    from git_undigest.formats import all_formats as _af

    d = _af()
    if name in d:
        from git_undigest.formats import unregister_format

        unregister_format(name)


def test_register_format_class() -> None:
    from git_undigest.formats import DigestFormat, register_format_class

    class TestFormat(DigestFormat):
        name = "test"

        def sniff(self, text: str) -> bool:
            return text.startswith("TEST:")

        def parse(self, text: str) -> tuple:
            return (), {}

        def parse_stream(self, text: str):
            return iter([])

        def serialize(self, repo) -> str:
            return "TEST:"

    register_format_class(TestFormat)
    try:
        from git_undigest.formats import get_format

        fmt = get_format("test")
        assert fmt is not None
        assert fmt.sniff("TEST:hello")
    finally:
        _cleanup_test_format()


def test_detect_format_from_instance() -> None:
    from git_undigest.formats import detect_format

    fmt = detect_format("File: x\n===")
    assert fmt is not None
    assert fmt.name == "gitingest"


# ---------------------------------------------------------------------------
# Utils extensions
# ---------------------------------------------------------------------------


def test_validate_base64() -> None:
    from git_undigest.utils import validate_base64

    assert validate_base64(base64.b64encode(b"data").decode("ascii"))
    assert not validate_base64("!!!")
    assert not validate_base64("")
    assert not validate_base64("   ")


def test_is_reserved_windows_name() -> None:
    from git_undigest.utils import is_reserved_windows_name

    assert is_reserved_windows_name("CON")
    assert is_reserved_windows_name("con.txt")
    assert is_reserved_windows_name("NUL")
    assert not is_reserved_windows_name("hello.txt")


# ---------------------------------------------------------------------------
# Integration: streaming pipeline
# ---------------------------------------------------------------------------


def test_streaming_pipeline(tmp_path: Path) -> None:
    digest_text = (
        "File: hello.txt\n"
        "=====\n"
        "Hello, World!\n"
        "=====\n"
        "File: nested/deep/file.py\n"
        "=====\n"
        "x = 1\n"
        "=====\n"
    )
    digest_path = tmp_path / "digest.txt"
    digest_path.write_text(digest_text)
    out = tmp_path / "repo"
    entries = list(parse_stream(digest_path))
    assert len(entries) == 2

    result = reconstruct_files_stream(iter(entries), out)
    assert len(result.created) == 2
    assert (out / "hello.txt").read_text().strip() == "Hello, World!"
    assert (out / "nested/deep/file.py").read_text().strip() == "x = 1"


def test_api_reconstruct_with_compressed_digest_unknown_extension(
    tmp_path: Path,
) -> None:
    digest_path = tmp_path / "digest.unknown"
    digest_path.write_text(SAMPLE_DIGEST)
    from git_undigest import reconstruct

    out = tmp_path / "out"
    result = reconstruct(digest_path, out)
    assert (out / "README.md").read_text().strip() == "# Hello"
    assert (out / "src/main.py").read_text().strip() == 'print("hello")'
    assert len(result.created) == 2
