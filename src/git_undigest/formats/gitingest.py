"""Parser for the GitIngest digest text format.

GitIngest (https://gitingest.com) produces digest files that look roughly
like::

    Directory structure:
    └── repo-name/
        ├── file1.py
        └── subdir/
            └── file2.py

    ================================================
    File: file1.py
    ================================================
    <file contents>

    ================================================
    File: subdir/file2.py
    ================================================
    <file contents>

This module implements :class:`GitIngestFormat`, a :class:`DigestFormat`
subclass.  :meth:`parse_stream` is the primary entry point — it uses a
5‑state line‑by‑line state machine, keeping memory proportional to the
largest file section rather than the full digest.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from typing import IO

from ..exceptions import DigestParseError, InvalidDigestError
from ..models import DigestSummary, FileEntry, Repository
from . import DigestFormat

_SEPARATOR_RE = re.compile(r"^={3,}\s*$", re.MULTILINE)
_FILE_HEADER_RE = re.compile(r"^(?:File|FILE):\s*(.+?)\s*$", re.MULTILINE)
_DIR_STRUCTURE_RE = re.compile(
    r"^Directory structure:\s*$", re.IGNORECASE | re.MULTILINE
)
_BINARY_SUFFIX_RE = re.compile(r"\s*\(base64\)\s*$", re.IGNORECASE)

# Maximum prefix size to examine for format sniffing.
_SNIFF_SIZE = 8192


class GitIngestFormat(DigestFormat):
    """Format plugin for GitIngest-style digests.

    :meth:`parse_stream` is the primary parser — it reads *stream*
    line‑by‑line, emitting each :class:`FileEntry` as its section
    completes.  :meth:`parse` is a convenience wrapper that fully
    consumes :meth:`parse_stream`.
    """

    name: str = "gitingest"

    # ------------------------------------------------------------------
    # Sniff
    # ------------------------------------------------------------------

    def sniff(self, prefix: str) -> bool:
        """Return True if *prefix* looks like a GitIngest digest.

        Args:
            prefix: Raw digest file contents (typically ≤8 KB).

        Returns:
            Whether the text appears to match the GitIngest format.
        """
        if not prefix or not prefix.strip():
            return False
        has_separator = bool(_SEPARATOR_RE.search(prefix))
        has_file_header = bool(_FILE_HEADER_RE.search(prefix))
        has_dir_structure = bool(_DIR_STRUCTURE_RE.search(prefix))
        return (has_separator and has_file_header) or has_dir_structure

    # ------------------------------------------------------------------
    # Parse (bulk — delegates to parse_stream)
    # ------------------------------------------------------------------

    def parse(self, text: str) -> DigestSummary:
        """Parse raw GitIngest digest text into a :class:`DigestSummary`.

        Delegates to :meth:`parse_stream` internally; no duplicated
        parsing logic.

        Args:
            text: The full raw text of a digest file.

        Returns:
            A populated :class:`DigestSummary`.

        Raises:
            InvalidDigestError: If the digest is empty or contains no file
                sections at all.
            DigestParseError: If a file header is malformed.
        """
        repo_name = self._detect_repo_name(text)
        entries = list(self.parse_stream(io.StringIO(text)))
        if not entries:
            raise InvalidDigestError(
                "No file sections found in digest. Expected GitIngest-style "
                "'File: <path>' headers between separator lines."
            )
        return DigestSummary(
            repo_name=repo_name,
            files=tuple(e.to_digest_file() for e in entries),
        )

    # ------------------------------------------------------------------
    # Parse streaming (line-by-line, constant memory)
    # ------------------------------------------------------------------

    def parse_stream(self, stream: IO[str]) -> Iterator[FileEntry]:
        """Parse a GitIngest digest stream, yielding files one at a time.

        Reads the stream line-by-line, emitting each :class:`FileEntry` as
        its section is fully received. Memory usage is O(max file size)
        rather than O(total digest size).

        Args:
            stream: An open text stream (e.g. ``open("digest.txt")``).

        Yields:
            :class:`FileEntry` for each complete file section.

        Raises:
            DigestParseError: If a file header is malformed.
            InvalidDigestError: If the digest contains no file sections.
        """
        # Phase 1: consume header lines (directory structure, etc.) until
        # the first separator line.
        header_lines: list[str] = []
        for line in stream:
            header_lines.append(line)
            if _SEPARATOR_RE.match(line.rstrip("\n\r")):
                break

        self._detect_repo_name("".join(header_lines))

        # Phase 2: stream file sections.
        seen_any_header = False
        buf: list[str] = []
        state: int = 0
        # state 0: looking for a separator or first File: header
        # state 1: got separator, looking for File: header
        # state 2: got File: header, looking for closing separator
        # state 3: in content, looking for next separator+File or EOF
        # state 4: separator seen in content — candidate for new section
        current_path: str | None = None
        current_is_binary: bool = False

        def _flush() -> Iterator[FileEntry]:
            nonlocal buf
            if current_path is not None:
                content_lines = [ln.rstrip("\n\r") for ln in buf]
                if content_lines and content_lines[-1] == "":
                    content_lines = content_lines[:-1]
                content_text = "\n".join(content_lines)
                if content_lines:
                    content_text += "\n"
                normalized = current_path.replace("\\", "/")
                encoded = content_text.encode("utf-8", errors="surrogateescape")
                yield FileEntry(
                    path=normalized,
                    content=content_text,
                    size=len(encoded),
                    is_binary=current_is_binary,
                    line_number=0,
                )
            buf = []

        def _line_iter() -> Iterator[str]:
            yield from header_lines
            yield from stream

        for raw_line in _line_iter():
            line = raw_line.rstrip("\n\r")

            if state == 0:
                if _SEPARATOR_RE.match(line):
                    state = 1
                elif _FILE_HEADER_RE.match(line):
                    seen_any_header = True
                    raw_header = _FILE_HEADER_RE.match(line).group(1).strip()  # type: ignore[union-attr]
                    current_is_binary = bool(_BINARY_SUFFIX_RE.search(raw_header))
                    current_path = _BINARY_SUFFIX_RE.sub("", raw_header).strip()
                    if not current_path:
                        raise DigestParseError("Empty filename in file header.")
                    state = 2
                continue

            if state == 1:
                header_match = _FILE_HEADER_RE.match(line)
                if header_match:
                    seen_any_header = True
                    raw_header = header_match.group(1).strip()
                    current_is_binary = bool(_BINARY_SUFFIX_RE.search(raw_header))
                    current_path = _BINARY_SUFFIX_RE.sub("", raw_header).strip()
                    if not current_path:
                        raise DigestParseError("Empty filename in file header.")
                    state = 2
                else:
                    state = 0
                continue

            if state == 2:
                if _SEPARATOR_RE.match(line):
                    state = 3
                else:
                    raise DigestParseError(
                        f"Malformed file section for {current_path!r}: "
                        "expected a separator line after the header.",
                    )
                continue

            if state == 3:
                if _SEPARATOR_RE.match(line):
                    state = 4
                    buf.append(raw_line)
                else:
                    buf.append(raw_line)
                continue

            if state == 4:
                header_match = _FILE_HEADER_RE.match(line)
                if header_match:
                    if buf and _SEPARATOR_RE.match(buf[-1].rstrip("\n\r")):
                        buf.pop()
                        yield from _flush()
                    seen_any_header = True
                    raw_header = header_match.group(1).strip()
                    current_is_binary = bool(_BINARY_SUFFIX_RE.search(raw_header))
                    current_path = _BINARY_SUFFIX_RE.sub("", raw_header).strip()
                    if not current_path:
                        raise DigestParseError("Empty filename in file header.")
                    state = 2
                else:
                    buf.append(raw_line)
                    state = 3
                continue

        if current_path is not None and state >= 2:
            if buf and _SEPARATOR_RE.match(buf[-1].rstrip("\n\r")):
                buf.pop()
            yield from _flush()

        if not seen_any_header:
            raise InvalidDigestError(
                "No file sections found in digest. Expected GitIngest-style "
                "'File: <path>' headers between separator lines."
            )

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------

    def serialize(self, repo: Repository) -> str:
        """Serialize a :class:`Repository` back to GitIngest digest format.

        Args:
            repo: The repository to serialize.

        Returns:
            A string containing the digest in GitIngest format.
        """
        parts: list[str] = []
        parts.append("Directory structure:")
        parts.append(self._render_tree(repo))

        for f in repo.files:
            parts.append("")
            parts.append("=" * 48)
            if f.is_binary:
                parts.append(f"File: {f.path} (base64)")
            else:
                parts.append(f"File: {f.path}")
            parts.append("=" * 48)
            parts.append(f.content)
            parts.append("")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_repo_name(text: str) -> str:
        """Best-effort extraction of the repository name from digest header
        material (the "Directory structure:" tree, if present).
        """
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if _DIR_STRUCTURE_RE.match(line):
                for follow in lines[i + 1 : i + 5]:
                    stripped = follow.strip()
                    stripped = re.sub(r"^[│├└─\s]+", "", stripped)
                    if stripped.endswith("/"):
                        return stripped.rstrip("/")
                break
        return "repository"

    @staticmethod
    def _render_tree(repo: Repository) -> str:
        """Render a directory tree string for the repository."""
        from typing import Any

        root: dict[str, dict[str, Any] | None] = {}
        for f in repo.files:
            parts = f.path.split("/")
            node = root
            for part in parts[:-1]:
                existing = node.get(part)
                if existing is None:
                    existing = {}
                    node[part] = existing
                node = existing
            node[parts[-1]] = None

        lines: list[str] = [f"└── {repo.name}/"]

        def _walk(node: dict[str, dict[str, Any] | None], prefix: str) -> None:
            entries = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0]))
            for idx, (name, child) in enumerate(entries):
                is_last = idx == len(entries) - 1
                connector = "└── " if is_last else "├── "
                suffix = "/" if isinstance(child, dict) else ""
                lines.append(f"{prefix}{connector}{name}{suffix}")
                if isinstance(child, dict):
                    extension = "    " if is_last else "│   "
                    _walk(child, prefix + extension)

        _walk(root, "")
        return "\n".join(lines)
