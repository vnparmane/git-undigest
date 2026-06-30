"""Tests for the formats registry, checksum helpers, and placeholders."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from git_undigest import checksum
from git_undigest.exceptions import (
    ChecksumMismatchError,
    InvalidDigestError,
    NotImplementedFeatureError,
    UnsupportedFormatError,
)
from git_undigest.formats import all_formats, detect_format, get_format, load_plugin
from git_undigest.parser import parse_compressed_digest
from git_undigest.writer import (
    reconstruct_binary_file,
    reconstruct_files_parallel,
    resume_reconstruction,
)


def test_gitingest_format_is_registered() -> None:
    names = {f.name for f in all_formats()}
    assert "gitingest" in names


def test_get_format_returns_registered_format() -> None:
    fmt = get_format("gitingest")
    assert fmt.name == "gitingest"


def test_detect_format_raises_for_unrecognized_text() -> None:
    with pytest.raises(UnsupportedFormatError):
        detect_format("this is not a digest of any known format")


def test_sha256_text_is_deterministic() -> None:
    h1 = checksum.sha256_text("hello world")
    h2 = checksum.sha256_text("hello world")
    assert h1 == h2
    assert len(h1) == 64


def test_verify_checksum_passes_for_matching_content() -> None:
    content = "hello"
    digest = checksum.sha256_text(content)
    checksum.verify_checksum("a.txt", content, digest)  # should not raise


def test_verify_checksum_raises_for_mismatch() -> None:
    with pytest.raises(ChecksumMismatchError):
        checksum.verify_checksum("a.txt", "hello", "0" * 64)


def test_verify_checksum_manifest_not_implemented() -> None:
    with pytest.raises(NotImplementedFeatureError):
        checksum.verify_checksum_manifest()


def test_parse_compressed_digest_with_missing_file(tmp_path: Path) -> None:
    """Now implemented — raises InvalidDigestError for missing file."""
    with pytest.raises(InvalidDigestError):
        parse_compressed_digest(tmp_path / "digest.txt.gz")


def test_reconstruct_binary_file(tmp_path: Path) -> None:
    payload = b"hello binary world"
    content = base64.b64encode(payload).decode("ascii")
    target = tmp_path / "out.bin"
    written = reconstruct_binary_file(target, content)
    assert written == len(payload)
    assert target.read_bytes() == payload


def test_reconstruct_binary_file_invalid_base64(tmp_path: Path) -> None:
    from git_undigest.exceptions import BinaryDecodeError

    with pytest.raises(BinaryDecodeError):
        reconstruct_binary_file(tmp_path / "out.bin", "not-base64!!!")


def test_reconstruct_files_parallel_not_implemented() -> None:
    with pytest.raises(NotImplementedFeatureError):
        reconstruct_files_parallel()


def test_resume_reconstruction_not_implemented() -> None:
    with pytest.raises(NotImplementedFeatureError):
        resume_reconstruction()


def test_load_plugin_with_missing_entry_point() -> None:
    """Now implemented — raises KeyError for missing entry point."""
    with pytest.raises(KeyError):
        load_plugin("some.entry.point")
