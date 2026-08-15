"""Executable contracts for machine-learning systems.

``mlcontract`` lets you declare the data and model interface an ML component
expects, then validate real data against that declaration, compare contract
versions, and fail CI when a change is breaking.

The public API is intentionally small. Everything exported here is covered by
the project's compatibility policy; anything not listed in :data:`__all__` is an
internal implementation detail and may change without notice.
"""

from __future__ import annotations

from mlcontract._version import __version__

__all__ = [
    "__version__",
]
