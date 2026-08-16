"""The ``mlcontract`` command-line interface.

See :mod:`mlcontract.cli.main` for the commands and their exit codes.

Note that the ``main`` *function* is deliberately not re-exported here. Binding
it in this namespace would shadow the ``main`` submodule of the same name, so
even ``import mlcontract.cli.main`` would hand back the function instead of the
module — a confusing failure with no obvious cause. Import it from its module:
``from mlcontract.cli.main import main``.
"""

from __future__ import annotations

from mlcontract.cli.main import ExitCode, run

__all__ = ["ExitCode", "run"]
