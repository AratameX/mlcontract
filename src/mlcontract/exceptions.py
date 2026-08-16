"""Exceptions and the machine-readable error-code registry.

Errors are part of this library's public interface. Users grep logs for codes,
alert on them, and assert on them in tests, so a code's meaning must never
change once released. Codes are therefore permanent: never reused, never
renumbered, and never repurposed. Retiring a code means marking it obsolete and
allocating a new one.

Codes are grouped by domain so the range alone tells you where a failure came
from:

===========  =====================================================
Range        Domain
===========  =====================================================
``MLC0xx``   Contract definition — the contract itself is invalid
``MLC1xx``   Structural validation — columns, order, dtypes
``MLC2xx``   Value constraints — nulls, ranges, categories, patterns
``MLC3xx``   Model metadata
``MLC4xx``   Predictions and outputs
``MLC5xx``   Metrics
``MLC6xx``   Compatibility and breaking changes
``MLC9xx``   Integrations and optional dependencies
===========  =====================================================

Only codes that are actually raised somewhere are registered. The registry grows
one release at a time rather than being reserved up front.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ErrorCode:
    """A permanent, machine-readable identifier for one failure mode.

    Attributes:
        code: The stable identifier, for example ``"MLC004"``.
        summary: A short description of what the code means. Safe to reword for
            clarity; the code itself is what callers depend on.
    """

    code: str
    summary: str

    def __str__(self) -> str:
        """Return the bare code, so codes interpolate cleanly into messages."""
        return self.code


# --------------------------------------------------------------------------
# MLC0xx — contract definition
# --------------------------------------------------------------------------

MLC001 = ErrorCode("MLC001", "Contract or feature name is missing or invalid")
MLC002 = ErrorCode("MLC002", "Unrecognised key in a contract document")
MLC003 = ErrorCode("MLC003", "Contract format version is not supported by this release")
MLC004 = ErrorCode("MLC004", "Contract version is not a valid semantic version")
MLC005 = ErrorCode("MLC005", "Duplicate feature name")
MLC006 = ErrorCode("MLC006", "Unknown data type")
MLC007 = ErrorCode("MLC007", "Constraint value is invalid")
MLC008 = ErrorCode("MLC008", "Constraint does not apply to this data type")
MLC009 = ErrorCode("MLC009", "Constraints contradict one another")
MLC010 = ErrorCode("MLC010", "Contract document is malformed")
MLC011 = ErrorCode("MLC011", "Required key is missing from a contract document")
MLC012 = ErrorCode("MLC012", "Contract declares no features")
MLC013 = ErrorCode("MLC013", "Declared previous name collides with a current feature name")
MLC014 = ErrorCode("MLC014", "Row-count bounds are invalid")

# --------------------------------------------------------------------------
# MLC1xx — structural validation
# --------------------------------------------------------------------------

MLC101 = ErrorCode("MLC101", "A required feature is missing from the data")
MLC102 = ErrorCode("MLC102", "The data contains a column the contract does not declare")
MLC103 = ErrorCode("MLC103", "Columns are not in the order the contract declares")
MLC104 = ErrorCode("MLC104", "A column's type does not satisfy the declared type")
MLC105 = ErrorCode("MLC105", "The dataset has fewer rows than the contract permits")
MLC106 = ErrorCode("MLC106", "The dataset has more rows than the contract permits")

# --------------------------------------------------------------------------
# MLC2xx — value constraints
# --------------------------------------------------------------------------

MLC201 = ErrorCode("MLC201", "Null values found in a column declared not nullable")
MLC202 = ErrorCode("MLC202", "The proportion of nulls exceeds the permitted maximum")
MLC203 = ErrorCode("MLC203", "Values fall below the declared minimum")
MLC204 = ErrorCode("MLC204", "Values exceed the declared maximum")
MLC205 = ErrorCode("MLC205", "Values fall outside the declared set of allowed values")
MLC206 = ErrorCode("MLC206", "Values do not match the declared pattern")
MLC207 = ErrorCode("MLC207", "Duplicate values found in a column declared unique")

# --------------------------------------------------------------------------
# MLC1xx — structural validation
# --------------------------------------------------------------------------

MLC101 = ErrorCode("MLC101", "A required feature is missing from the data")
MLC102 = ErrorCode("MLC102", "The data contains a column the contract does not declare")
MLC103 = ErrorCode("MLC103", "Columns are not in the order the contract declares")
MLC104 = ErrorCode("MLC104", "A column's type does not match the contract")
MLC105 = ErrorCode("MLC105", "The dataset has fewer rows than the contract permits")
MLC106 = ErrorCode("MLC106", "The dataset has more rows than the contract permits")

# --------------------------------------------------------------------------
# MLC2xx — value constraints
# --------------------------------------------------------------------------

MLC201 = ErrorCode("MLC201", "Null values in a feature declared not nullable")
MLC202 = ErrorCode("MLC202", "Proportion of nulls exceeds the permitted maximum")
MLC203 = ErrorCode("MLC203", "Values below the permitted minimum")
MLC204 = ErrorCode("MLC204", "Values above the permitted maximum")
MLC205 = ErrorCode("MLC205", "Values outside the permitted set")
MLC206 = ErrorCode("MLC206", "Values not matching the required pattern")
MLC207 = ErrorCode("MLC207", "Duplicate values in a feature declared unique")
MLC208 = ErrorCode("MLC208", "Values whose type does not match the contract")

# --------------------------------------------------------------------------
# MLC9xx — integrations
# --------------------------------------------------------------------------

MLC901 = ErrorCode("MLC901", "An optional dependency is required but not installed")
MLC902 = ErrorCode("MLC902", "The data is of a kind no adapter can read")


REGISTRY: dict[str, ErrorCode] = {
    code.code: code
    for code in (
        MLC001,
        MLC002,
        MLC003,
        MLC004,
        MLC005,
        MLC006,
        MLC007,
        MLC008,
        MLC009,
        MLC010,
        MLC011,
        MLC012,
        MLC013,
        MLC014,
        MLC101,
        MLC102,
        MLC103,
        MLC104,
        MLC105,
        MLC106,
        MLC201,
        MLC202,
        MLC203,
        MLC204,
        MLC205,
        MLC206,
        MLC207,
        MLC901,
        MLC902,
    )
}
"""Every error code this release can raise, keyed by its identifier."""


class MLContractError(Exception):
    """Base class for every error this library raises.

    Catching this catches everything from ``mlcontract`` and nothing else, so
    callers can wrap library calls without swallowing unrelated failures.

    Attributes:
        code: The :class:`ErrorCode` identifying this failure mode.
        context: Structured details about the failure — field names, expected
            and actual values. Present so failures can be inspected
            programmatically rather than parsed out of a message string.
    """

    def __init__(self, message: str, *, code: ErrorCode, **context: Any) -> None:
        self.code = code
        self.context = context
        self.message = message
        super().__init__(f"[{code.code}] {message}")


class ContractDefinitionError(MLContractError):
    """The contract itself is invalid.

    Raised while building or loading a contract — bad types, contradictory
    constraints, malformed documents. It means the contract cannot be used at
    all, as distinct from data failing to satisfy a valid contract.
    """


class ContractValidationError(MLContractError):
    """Data failed to satisfy a valid contract.

    Distinct from :class:`ContractDefinitionError`: the contract is fine, the
    data is not. Raised only by
    :meth:`~mlcontract.report.ValidationReport.raise_for_status`, never by
    validation itself — validation returns a report so that every problem is
    visible at once.

    Attributes:
        report: The full :class:`~mlcontract.report.ValidationReport`, so a
            caller catching this still has access to every violation rather than
            just the summary in the message.
    """

    def __init__(
        self, message: str, *, code: ErrorCode, report: Any = None, **context: Any
    ) -> None:
        super().__init__(message, code=code, **context)
        self.report = report


class SchemaValidationError(ContractValidationError):
    """The shape of the data is wrong — columns, ordering, types or row counts."""


class FeatureValidationError(ContractValidationError):
    """Individual values violate the constraints declared for their feature."""


class IntegrationError(MLContractError):
    """An optional dependency or third-party integration is unavailable.

    Always carries actionable installation guidance, because the alternative is
    a bare ``ImportError`` that tells the user nothing about which extra to
    install.
    """


def missing_dependency(package: str, extra: str, purpose: str) -> IntegrationError:
    """Build an :class:`IntegrationError` with a copy-pasteable install command.

    Args:
        package: The importable package that was missing, e.g. ``"yaml"``.
        extra: The mlcontract extra that provides it, e.g. ``"yaml"``.
        purpose: What the caller was trying to do, e.g. ``"read YAML contracts"``.

    Returns:
        An error whose message names the exact command to run.
    """
    return IntegrationError(
        f"{purpose} requires the optional '{extra}' extra, which provides "
        f'{package!r}. Install it with:\n\n    pip install "mlcontract[{extra}]"',
        code=MLC901,
        package=package,
        extra=extra,
    )
