"""Smoke tests for package metadata and importability."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import schemapact

# PEP 440: release segment, plus the pre/post/dev segments we actually use.
_PEP440 = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.dev\d+)?$")


def test_package_imports():
    assert schemapact is not None


def test_version_is_exported():
    assert isinstance(schemapact.__version__, str)
    assert schemapact.__version__


def test_version_is_pep440_compliant():
    assert _PEP440.match(schemapact.__version__), (
        f"{schemapact.__version__!r} is not a version this project knows how to release"
    )


def test_installed_metadata_matches_source():
    """The wheel's recorded version must equal the one in ``_version.py``.

    This is the check that catches a stale editable install or a build backend
    misconfiguration before it reaches a release tag.
    """
    assert importlib.metadata.version("schemapact") == schemapact.__version__


def test_py_typed_marker_is_shipped():
    """Without this file, type checkers silently ignore our annotations."""
    marker = Path(schemapact.__file__).parent / "py.typed"
    assert marker.is_file()
