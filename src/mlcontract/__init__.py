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
from mlcontract.compatibility import Compatibility, CompatibilityResult
from mlcontract.contract import SPEC_VERSION, Contract, Feature
from mlcontract.diff import Change, ChangeKind, ContractDiff, Impact, VersionBump
from mlcontract.dtypes import DType
from mlcontract.exceptions import (
    CompatibilityError,
    ContractDefinitionError,
    ContractValidationError,
    FeatureValidationError,
    IntegrationError,
    MLContractError,
    SchemaValidationError,
)
from mlcontract.report import Sample, Severity, ValidationReport, Violation


def validate(
    contract: Contract,
    data: object,
    *,
    sample_values: bool = True,
    max_samples: int = 5,
) -> ValidationReport:
    """Check data against a contract and return a report.

    A function-shaped alternative to :meth:`Contract.validate`, for code that
    reads better with the contract as an argument. The two are equivalent.

    Args:
        contract: The contract to check against.
        data: A list of mappings, a path to a ``.csv`` or ``.tsv`` file, or a
            pandas DataFrame if the ``pandas`` extra is installed.
        sample_values: Whether violations carry examples of offending values.
        max_samples: How many examples each violation carries.

    Returns:
        A report listing every violation found.
    """
    return contract.validate(data, sample_values=sample_values, max_samples=max_samples)


__all__ = [
    "SPEC_VERSION",
    "Change",
    "ChangeKind",
    "Compatibility",
    "CompatibilityError",
    "CompatibilityResult",
    "Contract",
    "ContractDefinitionError",
    "ContractDiff",
    "ContractValidationError",
    "DType",
    "Feature",
    "FeatureValidationError",
    "Impact",
    "IntegrationError",
    "MLContractError",
    "Sample",
    "SchemaValidationError",
    "Severity",
    "ValidationReport",
    "VersionBump",
    "Violation",
    "__version__",
    "validate",
]
