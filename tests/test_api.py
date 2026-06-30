"""Tests for the top-level git_undigest public API."""

from __future__ import annotations

from pathlib import Path

import pytest

import git_undigest as gu


def _write_digest(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "digest.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_reconstruct_end_to_end(tmp_path: Path, nested_digest: str) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    out = tmp_path / "repo"
    result = gu.reconstruct(str(digest_path), str(out))
    assert (out / "README.md").exists()
    assert (out / "src" / "nested" / "deep.py").exists()
    assert len(result.created) == 2


def test_validate_returns_summary(tmp_path: Path, simple_digest: str) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    summary = gu.validate(str(digest_path))
    assert summary.file_count == 1


def test_validate_raises_on_path_traversal(tmp_path: Path) -> None:
    digest = (
        "================================================\n"
        "File: ../../etc/passwd\n"
        "================================================\n"
        "x\n"
    )
    digest_path = _write_digest(tmp_path, digest)
    with pytest.raises(gu.PathTraversalError):
        gu.validate(str(digest_path))


def test_validate_raises_on_duplicates(tmp_path: Path) -> None:
    digest = (
        "================================================\n"
        "File: a.txt\n"
        "================================================\n"
        "1\n"
        "================================================\n"
        "File: a.txt\n"
        "================================================\n"
        "2\n"
    )
    digest_path = _write_digest(tmp_path, digest)
    with pytest.raises(gu.DuplicateFileError):
        gu.validate(str(digest_path))


def test_inspect_contains_expected_keys(tmp_path: Path, nested_digest: str) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    info = gu.inspect(str(digest_path))
    assert info["repo_name"] == "myrepo"
    assert info["file_count"] == 2
    assert "languages" in info
    assert "largest_files" in info
    assert "tree" in info
    assert "myrepo/" in info["tree"]


def test_stats_basic_fields(tmp_path: Path, nested_digest: str) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    s = gu.stats(str(digest_path))
    assert s.file_count == 2
    assert s.folder_count >= 1
    assert s.total_bytes > 0
    assert s.estimated_tokens >= 0


def test_list_files_sorted(tmp_path: Path, nested_digest: str) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    files = gu.list_files(str(digest_path))
    assert files == sorted(files)
    assert "README.md" in files
    assert "src/nested/deep.py" in files


def test_reconstruct_dry_run_does_not_write(tmp_path: Path, simple_digest: str) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "repo"
    result = gu.reconstruct(str(digest_path), str(out), dry_run=True)
    assert result.dry_run is True
    assert not out.exists()


def test_reconstruct_missing_digest_file_raises(tmp_path: Path) -> None:
    with pytest.raises(gu.InvalidDigestError):
        gu.reconstruct(str(tmp_path / "does_not_exist.txt"), str(tmp_path / "out"))
