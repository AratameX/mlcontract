"""Shared test helpers.

Optional extras are skipped per-test, never per-module. Skipping a whole file
because one optional dependency is missing silently drops the tests that did not
need it — which is exactly how the JSON serialisation tests stopped running in a
core-only environment while still reporting green locally.
"""

from __future__ import annotations

import importlib.util

import pytest

HAS_YAML = importlib.util.find_spec("yaml") is not None
"""Whether PyYAML is importable in this environment."""

requires_yaml = pytest.mark.skipif(not HAS_YAML, reason="requires the 'yaml' extra")
"""Skip a single test that genuinely needs PyYAML."""
