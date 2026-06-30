"""Small shared utility functions used across git-undigest modules."""

from __future__ import annotations

import base64
import binascii
from pathlib import Path


def human_size(num_bytes: float) -> str:
    """Format a byte count as a human readable string.

    Args:
        num_bytes: The number of bytes.

    Returns:
        A human friendly string such as ``"1.5 KB"`` or ``"42 B"``.
    """
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def estimate_tokens(text_length_chars: int) -> int:
    """Roughly estimate LLM token count from a character count.

    Uses the common heuristic of ~4 characters per token.

    Args:
        text_length_chars: Number of characters in the text.

    Returns:
        Estimated number of tokens (rounded up).
    """
    if text_length_chars <= 0:
        return 0
    return (text_length_chars + 3) // 4


def detect_language(extension: str) -> str | None:
    """Map a file extension to a human-readable language name.

    Args:
        extension: File extension without the leading dot, lowercase.

    Returns:
        The detected language name, or ``None`` if unknown.
    """
    mapping = {
        "py": "Python",
        "pyi": "Python",
        "js": "JavaScript",
        "jsx": "JavaScript",
        "mjs": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TypeScript",
        "java": "Java",
        "kt": "Kotlin",
        "kts": "Kotlin",
        "go": "Go",
        "rs": "Rust",
        "rb": "Ruby",
        "php": "PHP",
        "c": "C",
        "h": "C",
        "cpp": "C++",
        "cc": "C++",
        "cxx": "C++",
        "hpp": "C++",
        "cs": "C#",
        "swift": "Swift",
        "m": "Objective-C",
        "scala": "Scala",
        "sh": "Shell",
        "bash": "Shell",
        "zsh": "Shell",
        "ps1": "PowerShell",
        "html": "HTML",
        "htm": "HTML",
        "css": "CSS",
        "scss": "SCSS",
        "sass": "Sass",
        "less": "Less",
        "json": "JSON",
        "yaml": "YAML",
        "yml": "YAML",
        "toml": "TOML",
        "xml": "XML",
        "md": "Markdown",
        "markdown": "Markdown",
        "rst": "reStructuredText",
        "sql": "SQL",
        "dockerfile": "Dockerfile",
        "lua": "Lua",
        "r": "R",
        "jl": "Julia",
        "dart": "Dart",
        "ex": "Elixir",
        "exs": "Elixir",
        "erl": "Erlang",
        "hs": "Haskell",
        "clj": "Clojure",
        "vue": "Vue",
        "txt": "Text",
        "ini": "INI",
        "cfg": "Config",
        "gitignore": "Config",
        "makefile": "Makefile",
    }
    return mapping.get(extension.lower())


def is_probably_binary(content: str) -> bool:
    """Heuristically determine whether decoded text content looks binary.

    Checks for the presence of the NUL character or a high ratio of
    non-printable characters, which usually indicates the original content
    was binary data poorly represented as text.

    Args:
        content: The decoded text content to inspect.

    Returns:
        ``True`` if the content looks like it was originally binary.
    """
    if "\x00" in content:
        return True
    if not content:
        return False
    sample = content[:8192]
    non_printable = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\t\n\r")
    return (non_printable / max(len(sample), 1)) > 0.3


_WINDOWS_RESERVED = frozenset(
    [
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    ]
)


def is_reserved_windows_name(name: str) -> bool:
    """Check if *name* is a reserved Windows device name (CON, NUL, etc.).

    Args:
        name: A filename (leaf component only).

    Returns:
        True if the name (without extension) matches a reserved name.
    """
    stem = Path(name).stem.upper()
    return stem in _WINDOWS_RESERVED


def validate_base64(data: str) -> bool:
    """Check whether *data* is valid base64-encoded text.

    Args:
        data: A string to test.

    Returns:
        True if the string is valid base64, False otherwise.
    """
    if not data or not data.strip():
        return False
    try:
        base64.b64decode(data.strip(), validate=True)
        return True
    except (ValueError, binascii.Error):
        return False
