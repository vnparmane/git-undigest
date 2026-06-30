"""Pluggable digest format parsers.

To add support for a new digest format, subclass :class:`DigestFormat` and
register it with :func:`register_format_class`::

    from git_undigest.formats import DigestFormat, register_format_class

    class RepoMixFormat(DigestFormat):
        name = "repomix"

        def sniff(self, prefix: str) -> bool:
            return "This file is a merged representation" in prefix

        def parse_stream(self, stream: IO[str]) -> Iterator[FileEntry]:
            ...  # line-by-line parser

        def serialize(self, repo: Repository) -> str:
            ...

    register_format_class(RepoMixFormat)

The old function-based API (``register_format(name, sniff, parse)``) still
works but is deprecated — use the class-based API for new code.

Third-party plugins are auto-discovered via the ``git_undigest.formats``
entry point group (``importlib.metadata.entry_points``).

Package authors can distribute ``git-undigest-repomix`` and have it
discovered automatically.
"""

from __future__ import annotations

import abc
import io
from collections.abc import Callable, Iterator
from importlib.metadata import entry_points
from typing import IO

from ..models import DigestSummary, FileEntry, Repository

SniffFn = Callable[[str], bool]
ParseFn = Callable[[str], DigestSummary]


# ---------------------------------------------------------------------------
# DigestFormat abstract base class
# ---------------------------------------------------------------------------


class DigestFormat(abc.ABC):
    """Abstract base class for digest format plugins.

    Subclasses must set :attr:`name` and implement :meth:`sniff`,
    :meth:`parse_stream`, and :meth:`serialize`.

    :meth:`parse` has a default implementation that collects results from
    :meth:`parse_stream`.  Class-based formats should override
    :meth:`parse_stream` and let :meth:`parse` use the base default.

    Function-based formats (deprecated) override :meth:`parse` and let
    :meth:`parse_stream` use its base default.
    """

    name: str = ""

    @abc.abstractmethod
    def sniff(self, prefix: str) -> bool:
        """Return ``True`` if *prefix* looks like this format.

        ``prefix`` is the first ~8 KB of the digest file. Implementations
        must not require the full file content.

        Args:
            prefix: Beginning of the digest text (typically ≤8192 chars).

        Returns:
            Whether the prefix matches this format.
        """

    def parse(self, text: str) -> DigestSummary:
        """Parse raw digest text into a :class:`DigestSummary`.

        The default implementation collects :class:`FileEntry` objects from
        :meth:`parse_stream`.  Override this only for function-based formats
        that cannot implement :meth:`parse_stream`.

        Args:
            text: Full raw digest text.

        Returns:
            A populated :class:`DigestSummary`.
        """
        entries = list(self.parse_stream(io.StringIO(text)))
        if not entries:
            from ..exceptions import InvalidDigestError

            raise InvalidDigestError("No file sections found in digest.")
        return DigestSummary(
            repo_name="repository",
            files=tuple(e.to_digest_file() for e in entries),
        )

    @abc.abstractmethod
    def parse_stream(self, stream: IO[str]) -> Iterator[FileEntry]:
        """Parse a digest stream, yielding files one at a time.

        Args:
            stream: An open text stream (e.g. ``open("digest.txt")``).

        Yields:
            :class:`FileEntry` objects as each file section completes.

        Raises:
            DigestParseError: If a section is malformed.
            InvalidDigestError: If the digest contains no file sections.
        """

    @abc.abstractmethod
    def serialize(self, repo: Repository) -> str:
        """Serialize a :class:`Repository` back into this format's digest text.

        Args:
            repo: The repository to serialize.

        Returns:
            A string containing the digest in this format.
        """


# ---------------------------------------------------------------------------
# Backward-compatible function-based adapter
# ---------------------------------------------------------------------------


class _FunctionBasedFormat(DigestFormat):
    """Adapter that wraps old-style (sniff, parse) callables as a DigestFormat.

    ``parse_stream`` delegates to ``parse`` so callers that only have
    function-based plugins still get streaming support (at the cost of
    memory — the full text is loaded by ``parse``).
    """

    name: str

    def __init__(self, name: str, sniff_fn: SniffFn, parse_fn: ParseFn) -> None:
        self.name = name
        self._sniff_fn = sniff_fn
        self._parse_fn = parse_fn

    def sniff(self, prefix: str) -> bool:
        return self._sniff_fn(prefix)

    def parse(self, text: str) -> DigestSummary:
        return self._parse_fn(text)

    def parse_stream(self, stream: IO[str]) -> Iterator[FileEntry]:
        text = stream.read() if hasattr(stream, "read") else "".join(stream)
        summary = self.parse(text)
        for f in summary.files:
            yield FileEntry(
                path=f.path,
                content=f.content,
                size=f.size,
                line_number=f.line_number,
            )

    def serialize(self, repo: Repository) -> str:
        from ..exceptions import NotImplementedFeatureError

        raise NotImplementedFeatureError(
            f"Format {self.name!r} registered via legacy function API does"
            " not support serialize(). Use register_format_class() with a"
            " DigestFormat subclass."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, DigestFormat] = {}
"""All registered formats, keyed by name. Registration order is preserved."""


def register_format(name: str, sniff: SniffFn, parse: ParseFn) -> None:
    """Register a new digest format via the legacy function-based API.

    Consider using :func:`register_format_class` with a
    :class:`DigestFormat` subclass for new code — it supports streaming
    and serialization.

    Args:
        name: Unique short name for the format.
        sniff: Function that detects whether a prefix matches this format.
        parse: Function that parses raw text into a :class:`DigestSummary`.
    """
    _REGISTRY[name] = _FunctionBasedFormat(name, sniff, parse)


def register_format_class(cls: type[DigestFormat]) -> None:
    """Register a :class:`DigestFormat` subclass.

    The class is instantiated once and stored. Subclasses must have a
    non-empty ``name`` class variable.

    Args:
        cls: A :class:`DigestFormat` subclass.

    Raises:
        ValueError: If ``cls.name`` is empty.
    """
    if not cls.name:
        msg = f"Cannot register format class {cls.__name__!r} with empty 'name'"
        raise ValueError(msg)
    _REGISTRY[cls.name] = cls()


def get_format(name: str) -> DigestFormat:
    """Look up a registered format by name.

    Args:
        name: The format's registered name.

    Returns:
        The matching :class:`DigestFormat`.

    Raises:
        KeyError: If no format with that name is registered.
    """
    if name not in _REGISTRY:
        avail = ", ".join(_REGISTRY) or "(none)"
        msg = f"No format registered with name {name!r}. Available: {avail}"
        raise KeyError(msg)
    return _REGISTRY[name]


def all_formats() -> tuple[DigestFormat, ...]:
    """Return all currently registered formats, in registration order."""
    return tuple(_REGISTRY.values())


def unregister_format(name: str) -> None:
    """Remove a registered format by name.

    Args:
        name: The format's registered name.

    Raises:
        KeyError: If no format with that name is registered.
    """
    if name not in _REGISTRY:
        avail = ", ".join(_REGISTRY) or "(none)"
        msg = f"No format registered with name {name!r}. Available: {avail}"
        raise KeyError(msg)
    del _REGISTRY[name]


def detect_format(prefix: str) -> DigestFormat:
    """Detect which registered format best matches the given text prefix.

    Args:
        prefix: Beginning of the digest text (typically ≤8192 chars).

    Returns:
        The first matching :class:`DigestFormat`.

    Raises:
        UnsupportedFormatError: If no registered format matches.
    """
    from ..exceptions import UnsupportedFormatError

    for fmt in _REGISTRY.values():
        if fmt.sniff(prefix):
            return fmt
    registered = ", ".join(_REGISTRY) or "(none)"
    raise UnsupportedFormatError(
        f"No registered digest format recognizes this file."
        f" Registered formats: {registered}"
    )


def discover_plugins() -> None:
    """Discover and register third-party format plugins via entry points.

    Scans the ``git_undigest.formats`` entry point group using
    ``importlib.metadata.entry_points``. Each entry point should point to a
    :class:`DigestFormat` subclass.

    Called automatically at import time.
    """
    eps = entry_points(group="git_undigest.formats")

    for ep in eps:
        try:
            cls = ep.load()
            if (
                isinstance(cls, type)
                and issubclass(cls, DigestFormat)
                and cls is not DigestFormat
            ):
                register_format_class(cls)
        except Exception:  # noqa: BLE001
            pass


def load_plugin(entry_point_name: str) -> None:
    """Load and register a single third-party format plugin by entry-point name.

    Args:
        entry_point_name: The name of an entry point in the
            ``git_undigest.formats`` group (e.g. ``"repomix"``).

    Raises:
        KeyError: If no entry point with that name is found.
    """
    eps = entry_points(group="git_undigest.formats")

    matched = [ep for ep in eps if ep.name == entry_point_name]
    if not matched:
        msg = f"No entry point named {entry_point_name!r} in git_undigest.formats group"
        raise KeyError(msg)

    cls = matched[0].load()
    if (
        isinstance(cls, type)
        and issubclass(cls, DigestFormat)
        and cls is not DigestFormat
    ):
        register_format_class(cls)


# ---------------------------------------------------------------------------
# Built-in format registration
# ---------------------------------------------------------------------------

from . import gitingest as _gitingest  # noqa: E402

register_format_class(_gitingest.GitIngestFormat)

__all__ = [
    "DigestFormat",
    "register_format",
    "register_format_class",
    "unregister_format",
    "get_format",
    "all_formats",
    "detect_format",
    "discover_plugins",
    "load_plugin",
]
