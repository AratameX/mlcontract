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
``SPX0xx``   Contract definition — the contract itself is invalid
``SPX1xx``   Structural validation — columns, order, dtypes
``SPX2xx``   Value constraints — nulls, ranges, categories, patterns
``SPX3xx``   Model metadata
``SPX4xx``   Predictions and outputs
``SPX5xx``   Metrics
``SPX6xx``   Compatibility and breaking changes
``SPX9xx``   Integrations and optional dependencies
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
        code: The stable identifier, for example ``"SPX004"``.
        summary: A short description of what the code means. Safe to reword for
            clarity; the code itself is what callers depend on.
    """

    code: str
    summary: str

    def __str__(self) -> str:
        """Return the bare code, so codes interpolate cleanly into messages."""
        return self.code


# --------------------------------------------------------------------------
# SPX0xx — contract definition
# --------------------------------------------------------------------------

SPX001 = ErrorCode("SPX001", "Contract or feature name is missing or invalid")
SPX002 = ErrorCode("SPX002", "Unrecognised key in a contract document")
SPX003 = ErrorCode("SPX003", "Contract format version is not supported by this release")
SPX004 = ErrorCode("SPX004", "Contract version is not a valid semantic version")
SPX005 = ErrorCode("SPX005", "Duplicate feature name")
SPX006 = ErrorCode("SPX006", "Unknown data type")
SPX007 = ErrorCode("SPX007", "Constraint value is invalid")
SPX008 = ErrorCode("SPX008", "Constraint does not apply to this data type")
SPX009 = ErrorCode("SPX009", "Constraints contradict one another")
SPX010 = ErrorCode("SPX010", "Contract document is malformed")
SPX011 = ErrorCode("SPX011", "Required key is missing from a contract document")
SPX012 = ErrorCode("SPX012", "Contract declares no features")
SPX013 = ErrorCode("SPX013", "Declared previous name collides with a current feature name")
SPX014 = ErrorCode("SPX014", "Row-count bounds are invalid")

# --------------------------------------------------------------------------
# SPX1xx — structural validation
# --------------------------------------------------------------------------

SPX101 = ErrorCode("SPX101", "A required feature is missing from the data")
SPX102 = ErrorCode("SPX102", "The data contains a column the contract does not declare")
SPX103 = ErrorCode("SPX103", "Columns are not in the order the contract declares")
SPX104 = ErrorCode("SPX104", "A column's type does not satisfy the declared type")
SPX105 = ErrorCode("SPX105", "The dataset has fewer rows than the contract permits")
SPX106 = ErrorCode("SPX106", "The dataset has more rows than the contract permits")

# --------------------------------------------------------------------------
# SPX2xx — value constraints
# --------------------------------------------------------------------------

SPX201 = ErrorCode("SPX201", "Null values found in a column declared not nullable")
SPX202 = ErrorCode("SPX202", "The proportion of nulls exceeds the permitted maximum")
SPX203 = ErrorCode("SPX203", "Values fall below the declared minimum")
SPX204 = ErrorCode("SPX204", "Values exceed the declared maximum")
SPX205 = ErrorCode("SPX205", "Values fall outside the declared set of allowed values")
SPX206 = ErrorCode("SPX206", "Values do not match the declared pattern")
SPX207 = ErrorCode("SPX207", "Duplicate values found in a column declared unique")

# --------------------------------------------------------------------------
# SPX1xx — structural validation
# --------------------------------------------------------------------------

SPX101 = ErrorCode("SPX101", "A required feature is missing from the data")
SPX102 = ErrorCode("SPX102", "The data contains a column the contract does not declare")
SPX103 = ErrorCode("SPX103", "Columns are not in the order the contract declares")
SPX104 = ErrorCode("SPX104", "A column's type does not match the contract")
SPX105 = ErrorCode("SPX105", "The dataset has fewer rows than the contract permits")
SPX106 = ErrorCode("SPX106", "The dataset has more rows than the contract permits")

# --------------------------------------------------------------------------
# SPX2xx — value constraints
# --------------------------------------------------------------------------

SPX201 = ErrorCode("SPX201", "Null values in a feature declared not nullable")
SPX202 = ErrorCode("SPX202", "Proportion of nulls exceeds the permitted maximum")
SPX203 = ErrorCode("SPX203", "Values below the permitted minimum")
SPX204 = ErrorCode("SPX204", "Values above the permitted maximum")
SPX205 = ErrorCode("SPX205", "Values outside the permitted set")
SPX206 = ErrorCode("SPX206", "Values not matching the required pattern")
SPX207 = ErrorCode("SPX207", "Duplicate values in a feature declared unique")
SPX208 = ErrorCode("SPX208", "Values whose type does not match the contract")

# --------------------------------------------------------------------------
# SPX6xx — compatibility
# --------------------------------------------------------------------------

SPX601 = ErrorCode("SPX601", "A change breaks compatibility in the direction checked")
SPX602 = ErrorCode("SPX602", "The declared version increment is smaller than the changes require")

# --------------------------------------------------------------------------
# SPX9xx — integrations
# --------------------------------------------------------------------------

SPX901 = ErrorCode("SPX901", "An optional dependency is required but not installed")
SPX902 = ErrorCode("SPX902", "The data is of a kind no adapter can read")


REGISTRY: dict[str, ErrorCode] = {
    code.code: code
    for code in (
        SPX001,
        SPX002,
        SPX003,
        SPX004,
        SPX005,
        SPX006,
        SPX007,
        SPX008,
        SPX009,
        SPX010,
        SPX011,
        SPX012,
        SPX013,
        SPX014,
        SPX101,
        SPX102,
        SPX103,
        SPX104,
        SPX105,
        SPX106,
        SPX201,
        SPX202,
        SPX203,
        SPX204,
        SPX205,
        SPX206,
        SPX207,
        SPX901,
        SPX902,
    )
}
"""Every error code this release can raise, keyed by its identifier."""


class SchemaPactError(Exception):
    """Base class for every error this library raises.

    Catching this catches everything from ``schemapact`` and nothing else, so
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


class ContractDefinitionError(SchemaPactError):
    """The contract itself is invalid.

    Raised while building or loading a contract — bad types, contradictory
    constraints, malformed documents. It means the contract cannot be used at
    all, as distinct from data failing to satisfy a valid contract.
    """


class ContractValidationError(SchemaPactError):
    """Data failed to satisfy a valid contract.

    Distinct from :class:`ContractDefinitionError`: the contract is fine, the
    data is not. Raised only by
    :meth:`~schemapact.report.ValidationReport.raise_for_status`, never by
    validation itself — validation returns a report so that every problem is
    visible at once.

    Attributes:
        report: The full :class:`~schemapact.report.ValidationReport`, so a
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


class CompatibilityError(SchemaPactError):
    """A contract change is not compatible in the direction that was required.

    Raised only when a caller asks for it, via
    :meth:`~schemapact.compatibility.CompatibilityResult.raise_for_status`.
    Comparing contracts returns a result by default, because knowing *which*
    changes broke compatibility is the entire point.

    Attributes:
        result: The full
            :class:`~schemapact.compatibility.CompatibilityResult`.
    """

    def __init__(
        self, message: str, *, code: ErrorCode, result: Any = None, **context: Any
    ) -> None:
        super().__init__(message, code=code, **context)
        self.result = result


class IntegrationError(SchemaPactError):
    """An optional dependency or third-party integration is unavailable.

    Always carries actionable installation guidance, because the alternative is
    a bare ``ImportError`` that tells the user nothing about which extra to
    install.
    """


def missing_dependency(package: str, extra: str, purpose: str) -> IntegrationError:
    """Build an :class:`IntegrationError` with a copy-pasteable install command.

    Args:
        package: The importable package that was missing, e.g. ``"yaml"``.
        extra: The schemapact extra that provides it, e.g. ``"yaml"``.
        purpose: What the caller was trying to do, e.g. ``"read YAML contracts"``.

    Returns:
        An error whose message names the exact command to run.
    """
    return IntegrationError(
        f"{purpose} requires the optional '{extra}' extra, which provides "
        f'{package!r}. Install it with:\n\n    pip install "schemapact[{extra}]"',
        code=SPX901,
        package=package,
        extra=extra,
    )
