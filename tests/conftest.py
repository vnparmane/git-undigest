"""Shared pytest fixtures for git-undigest tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def simple_digest() -> str:
    return (
        "================================================\n"
        "File: README.md\n"
        "================================================\n"
        "# Hello\n"
        "\n"
        "World.\n"
    )


@pytest.fixture
def nested_digest() -> str:
    return (
        "Directory structure:\n"
        "└── myrepo/\n"
        "    ├── README.md\n"
        "    └── src/\n"
        "        └── nested/\n"
        "            └── deep.py\n"
        "\n"
        "================================================\n"
        "File: README.md\n"
        "================================================\n"
        "# myrepo\n"
        "\n"
        "================================================\n"
        "File: src/nested/deep.py\n"
        "================================================\n"
        "x = 1\n"
    )
