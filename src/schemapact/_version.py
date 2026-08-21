"""Single source of truth for the package version.

The version is read here by ``pyproject.toml`` (via ``tool.setuptools.dynamic``),
re-exported from :mod:`schemapact`, reported by the CLI, and embedded in every
validation report and benchmark result. It is defined in exactly one place so a
release can never disagree with itself.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"
