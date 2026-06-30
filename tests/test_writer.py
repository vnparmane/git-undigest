"""Tests for git_undigest.writer covering overwrite/skip/backup/dry-run."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_undigest.exceptions import FileExistsConflictError
from git_undigest.models import DigestFile, DigestSummary
from git_undigest.writer import reconstruct_files


def _summary(*files: DigestFile) -> DigestSummary:
    return DigestSummary(repo_name="repo", files=files)


def test_writer_creates_files_and_directories(tmp_path: Path) -> None:
    summary = _summary(
        DigestFile(path="a.txt", content="hello", size=5),
        DigestFile(path="nested/dir/b.txt", content="world", size=5),
    )
    result = reconstruct_files(summary, tmp_path / "out")
    assert (tmp_path / "out" / "a.txt").read_text() == "hello"
    assert (tmp_path / "out" / "nested" / "dir" / "b.txt").read_text() == "world"
    assert len(result.created) == 2


def test_writer_raises_on_existing_file_without_policy(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    summary = _summary(DigestFile(path="a.txt", content="new", size=3))
    with pytest.raises(FileExistsConflictError):
        reconstruct_files(summary, out)
    # original content must be untouched
    assert (out / "a.txt").read_text() == "old"


def test_writer_overwrite_mode(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    summary = _summary(DigestFile(path="a.txt", content="new", size=3))
    result = reconstruct_files(summary, out, overwrite=True)
    assert (out / "a.txt").read_text() == "new"
    assert len(result.overwritten) == 1


def test_writer_skip_existing_mode(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    summary = _summary(DigestFile(path="a.txt", content="new", size=3))
    result = reconstruct_files(summary, out, skip_existing=True)
    assert (out / "a.txt").read_text() == "old"
    assert len(result.skipped) == 1


def test_writer_backup_mode(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    summary = _summary(DigestFile(path="a.txt", content="new", size=3))
    result = reconstruct_files(summary, out, backup=True)
    assert (out / "a.txt").read_text() == "new"
    assert (out / "a.txt.bak").read_text() == "old"
    assert len(result.backed_up) == 1


def test_writer_backup_mode_no_collision_on_repeated_runs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("v1")
    summary = _summary(DigestFile(path="a.txt", content="v2", size=2))
    reconstruct_files(summary, out, backup=True)
    summary2 = _summary(DigestFile(path="a.txt", content="v3", size=2))
    reconstruct_files(summary2, out, backup=True)
    assert (out / "a.txt").read_text() == "v3"
    assert (out / "a.txt.bak").exists()
    assert (out / "a.txt.bak.1").exists()


def test_writer_dry_run_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = _summary(DigestFile(path="a.txt", content="hello", size=5))
    result = reconstruct_files(summary, out, dry_run=True)
    assert not out.exists()
    assert result.dry_run is True
    assert len(result.created) == 1
    assert result.created[0].action == "would_create"


def test_writer_dry_run_reports_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_text("old")
    summary = _summary(DigestFile(path="a.txt", content="new", size=3))
    result = reconstruct_files(summary, out, overwrite=True, dry_run=True)
    assert (out / "a.txt").read_text() == "old"  # untouched
    assert len(result.overwritten) == 1


def test_writer_empty_file_content(tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = _summary(DigestFile(path="empty.txt", content="", size=0))
    reconstruct_files(summary, out)
    assert (out / "empty.txt").read_text() == ""


def test_writer_rejects_path_traversal(tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = _summary(DigestFile(path="../escape.txt", content="evil", size=4))
    from git_undigest.exceptions import PathTraversalError

    with pytest.raises(PathTraversalError):
        reconstruct_files(summary, out)
    assert not (tmp_path / "escape.txt").exists()


def test_writer_large_file(tmp_path: Path) -> None:
    out = tmp_path / "out"
    big_content = "x" * 5_000_000
    summary = _summary(
        DigestFile(path="big.txt", content=big_content, size=len(big_content))
    )
    reconstruct_files(summary, out)
    assert (out / "big.txt").stat().st_size == 5_000_000


def test_writer_unicode_content_and_filename(tmp_path: Path) -> None:
    out = tmp_path / "out"
    summary = _summary(
        DigestFile(path="résumé/文档.txt", content="héllo 你好 🎉", size=10)
    )
    reconstruct_files(summary, out)
    written = out / "résumé" / "文档.txt"
    assert written.read_text(encoding="utf-8") == "héllo 你好 🎉"
