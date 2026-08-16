"""Executable contracts for machine-learning systems.

``mlcontract`` lets you declare the data and model interface an ML component
expects, then validate real data against that declaration, compare contract
versions, and fail CI when a change is breaking.

The public API is intentionally small. Everything exported here is covered by
the project's compatibility policy; anything not listed in :data:`__all__` is an
internal implementation detail and may change without notice.

Example:
    >>> from mlcontract import Contract, DType, Feature
    >>> contract = Contract(
    ...     name="customer_features",
    ...     version="1.0.0",
    ...     features=[Feature("age", DType.INTEGER, nullable=False, min=18)],
    ... )
    >>> Contract.from_json(contract.to_json()) == contract
    True
"""

from __future__ import annotations

from mlcontract._version import __version__
from mlcontract.contract import SPEC_VERSION, Contract, Feature
from mlcontract.dtypes import DType
from mlcontract.exceptions import (
    ContractDefinitionError,
    IntegrationError,
    MLContractError,
)

__all__ = [
    "SPEC_VERSION",
    "Contract",
    "ContractDefinitionError",
    "DType",
    "Feature",
    "IntegrationError",
    "MLContractError",
    "__version__",
]
