"""Tests for git_undigest.cli."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_undigest.cli import main


def _write_digest(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "digest.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_cli_default_reconstruct(
    tmp_path: Path, simple_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "out"
    code = main([str(digest_path), str(out)])
    assert code == 0
    assert (out / "README.md").exists()


def test_cli_validate_command(
    tmp_path: Path, simple_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    code = main(["validate", str(digest_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "OK" in captured.out


def test_cli_list_command(
    tmp_path: Path, nested_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    code = main(["list", str(digest_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "README.md" in captured.out


def test_cli_stats_command(
    tmp_path: Path, nested_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    code = main(["stats", str(digest_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "Files:" in captured.out


def test_cli_inspect_command(
    tmp_path: Path, nested_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, nested_digest)
    code = main(["inspect", str(digest_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "Repository:" in captured.out


def test_cli_reconstruct_conflict_returns_error_code(
    tmp_path: Path, simple_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "out"
    main([str(digest_path), str(out)])
    code = main([str(digest_path), str(out)])
    captured = capsys.readouterr()
    assert code == 1
    assert "error" in captured.err


def test_cli_path_traversal_returns_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    digest = (
        "================================================\n"
        "File: ../escape.txt\n"
        "================================================\n"
        "evil\n"
    )
    digest_path = _write_digest(tmp_path, digest)
    code = main([str(digest_path), str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert code == 1
    assert "error" in captured.err


def test_cli_dry_run_flag(
    tmp_path: Path, simple_digest: str, capsys: pytest.CaptureFixture[str]
) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "out"
    code = main([str(digest_path), str(out), "--dry-run"])
    assert code == 0
    assert not out.exists()


def test_cli_overwrite_flag(tmp_path: Path, simple_digest: str) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "out"
    main([str(digest_path), str(out)])
    code = main([str(digest_path), str(out), "--overwrite"])
    assert code == 0


def test_cli_backup_flag(tmp_path: Path, simple_digest: str) -> None:
    digest_path = _write_digest(tmp_path, simple_digest)
    out = tmp_path / "out"
    main([str(digest_path), str(out)])
    code = main([str(digest_path), str(out), "--backup"])
    assert code == 0
    assert (out / "README.md.bak").exists()
