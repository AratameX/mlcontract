"""The validation engine.

Nothing in this module knows what kind of data it is looking at. It sees only a
:class:`~mlcontract._protocols.DataSource`, which is what lets one engine serve
``list[dict]``, CSV, pandas and everything added later.

Checks run in two passes, in this order:

1. **Structural** — row counts, missing features, unexpected columns, column
   order, column types.
2. **Value-level** — nulls, ranges, allowed values, patterns, uniqueness.

The ordering is not cosmetic. Structural failures make value checks meaningless
or actively misleading: a missing column has no values to be out of range, and a
column that turned out to hold strings cannot be compared against a numeric
minimum without raising. So a feature that fails its structural checks is
skipped for value checks, and the report says why rather than burying the real
problem under a pile of consequences.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from mlcontract._protocols import DataSource, column_values
from mlcontract.contract import Contract, Feature
from mlcontract.exceptions import (
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
    ErrorCode,
)
from mlcontract.report import Sample, Severity, ValidationReport, Violation

DEFAULT_MAX_SAMPLES = 5
"""How many offending values a violation carries unless told otherwise."""


def run(
    contract: Contract,
    source: DataSource,
    *,
    sample_values: bool = True,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> ValidationReport:
    """Validate a data source against a contract.

    Args:
        contract: The contract to check against.
        source: The data, behind the adapter protocol.
        sample_values: Whether violations carry offending values. Samples make a
            report far more actionable, but they are raw data — turn this off
            when reports go somewhere that should not see the underlying values.
        max_samples: How many values each violation carries.

    Returns:
        A report listing every violation found. Never raises for invalid data.
    """
    settings = _Settings(sample_values=sample_values, max_samples=max(0, max_samples))
    columns = source.column_names()
    present = set(columns)

    violations: list[Violation] = []
    violations.extend(_check_row_count(contract, source))
    violations.extend(_check_columns(contract, columns, present))

    for feature in contract.features:
        if feature.name not in present:
            continue
        violations.extend(_check_feature(feature, source, settings))

    return ValidationReport(
        contract_name=contract.name,
        contract_version=contract.version,
        source=source.describe(),
        row_count=source.row_count(),
        violations=tuple(violations),
    )


class _Settings:
    """How much detail violations should carry."""

    __slots__ = ("max_samples", "sample_values")

    def __init__(self, *, sample_values: bool, max_samples: int) -> None:
        self.sample_values = sample_values
        self.max_samples = max_samples

    def take(self, pairs: list[tuple[int, Any]]) -> tuple[Sample, ...]:
        """Return up to ``max_samples`` samples, or none if samples are disabled."""
        if not self.sample_values:
            return ()
        return tuple(Sample(row=row, value=value) for row, value in pairs[: self.max_samples])


# --------------------------------------------------------------------------
# Structural checks
# --------------------------------------------------------------------------


def _check_row_count(contract: Contract, source: DataSource) -> list[Violation]:
    """Check the dataset size against the contract's bounds."""
    rows = source.row_count()
    found: list[Violation] = []

    if contract.min_rows is not None and rows < contract.min_rows:
        found.append(
            Violation(
                code=MLC105,
                severity=Severity.ERROR,
                message=f"Dataset has {rows} rows, fewer than the required minimum of "
                f"{contract.min_rows}.",
                rule="min_rows",
                expected=contract.min_rows,
                actual=rows,
                remediation="Check the upstream extract completed; a short dataset usually "
                "means a partial load rather than genuinely missing data.",
            )
        )

    if contract.max_rows is not None and rows > contract.max_rows:
        found.append(
            Violation(
                code=MLC106,
                severity=Severity.ERROR,
                message=f"Dataset has {rows} rows, more than the permitted maximum of "
                f"{contract.max_rows}.",
                rule="max_rows",
                expected=contract.max_rows,
                actual=rows,
                remediation="Check for duplicated loads or an unfiltered join.",
            )
        )
    return found


def _check_columns(
    contract: Contract, columns: tuple[str, ...], present: set[str]
) -> list[Violation]:
    """Check which columns exist, whether extras are allowed, and their order."""
    found: list[Violation] = []

    for feature in contract.features:
        if feature.name in present:
            continue
        if feature.required:
            renamed = [name for name in feature.previous_names if name in present]
            hint = (
                f"The data has {renamed[0]!r}, which this feature declares as a previous "
                f"name — the rename has not been applied upstream."
                if renamed
                else f"Add the column, or mark {feature.name!r} optional with required=False."
            )
            found.append(
                Violation(
                    code=MLC101,
                    severity=Severity.ERROR,
                    message=f"Required feature {feature.name!r} is missing from the data.",
                    feature=feature.name,
                    rule="required",
                    expected=feature.name,
                    actual=None,
                    remediation=hint,
                )
            )

    declared = set(contract.feature_names)
    extras = [name for name in columns if name not in declared]
    if extras:
        # Undeclared columns are usually harmless — data carries more than any
        # one model needs — so they are a warning unless the contract says
        # otherwise. Reported either way, because a surprise column is often the
        # first visible sign of an upstream schema change.
        severity = Severity.ERROR if not contract.allow_extra_columns else Severity.WARNING
        found.append(
            Violation(
                code=MLC102,
                severity=severity,
                message=f"Data contains {len(extras)} column(s) the contract does not "
                f"declare: {', '.join(repr(name) for name in extras)}.",
                rule="allow_extra_columns",
                expected="only declared columns" if not contract.allow_extra_columns else None,
                actual=list(extras),
                remediation="Declare them in the contract, or set allow_extra_columns=false "
                "if they should be rejected."
                if contract.allow_extra_columns
                else "Remove the columns, or declare them in the contract.",
            )
        )

    if contract.enforce_column_order:
        expected_order = [name for name in contract.feature_names if name in present]
        actual_order = [name for name in columns if name in declared]
        if expected_order != actual_order:
            found.append(
                Violation(
                    code=MLC103,
                    severity=Severity.ERROR,
                    message="Declared columns are not in the order the contract requires.",
                    rule="enforce_column_order",
                    expected=expected_order,
                    actual=actual_order,
                    remediation="Reorder the columns, or set enforce_column_order=false if "
                    "order does not matter to consumers.",
                )
            )
    return found


# --------------------------------------------------------------------------
# Per-feature checks
# --------------------------------------------------------------------------


def _check_feature(feature: Feature, source: DataSource, settings: _Settings) -> list[Violation]:
    """Check one present column: its type first, then its values."""
    found: list[Violation] = []

    observed = source.observed_dtype(feature.name)
    type_ok = observed is not None and feature.dtype.accepts(observed)

    if not type_ok:
        actual = str(observed) if observed is not None else "mixed"
        found.append(
            Violation(
                code=MLC104,
                severity=Severity.ERROR,
                message=f"Column {feature.name!r} holds {actual} values but the contract "
                f"declares {feature.dtype}.",
                feature=feature.name,
                rule="dtype",
                expected=str(feature.dtype),
                actual=actual,
                remediation="Cast the column upstream, or change the declared type if the "
                "new type is correct."
                if observed is not None
                else "The column holds more than one type of value. Clean it upstream.",
            )
        )

    found.extend(_check_nulls(feature, source, settings))

    if not type_ok:
        # Comparing a string against a numeric minimum would raise, and every
        # value would be reported as violating every rule. The type failure
        # above is the real problem; piling consequences on top hides it.
        return found

    found.extend(_check_range(feature, source, settings))
    found.extend(_check_allowed_values(feature, source, settings))
    found.extend(_check_pattern(feature, source, settings))
    found.extend(_check_unique(feature, source, settings))
    return found


def _check_nulls(feature: Feature, source: DataSource, settings: _Settings) -> list[Violation]:
    """Check nullability and the permitted null fraction."""
    nulls = source.null_count(feature.name)
    if nulls == 0:
        return []

    rows = source.row_count()
    fraction = nulls / rows if rows else 0.0

    if not feature.nullable:
        return [
            Violation(
                code=MLC201,
                severity=Severity.ERROR,
                message=f"Column {feature.name!r} is declared not nullable but has "
                f"{nulls} null value(s).",
                feature=feature.name,
                rule="nullable",
                expected=0,
                actual=nulls,
                affected_rows=nulls,
                remediation="Fill or drop the null rows, or set nullable=true if nulls are "
                "legitimate here.",
            )
        ]

    if feature.max_null_fraction is not None and fraction > feature.max_null_fraction:
        return [
            Violation(
                code=MLC202,
                severity=Severity.ERROR,
                message=f"Column {feature.name!r} is {fraction:.1%} null, above the permitted "
                f"maximum of {feature.max_null_fraction:.1%}.",
                feature=feature.name,
                rule="max_null_fraction",
                expected=feature.max_null_fraction,
                actual=round(fraction, 6),
                affected_rows=nulls,
                remediation="Investigate why coverage dropped; this usually means an upstream "
                "join started missing rows.",
            )
        ]
    return []


def _check_range(feature: Feature, source: DataSource, settings: _Settings) -> list[Violation]:
    """Check values against the declared minimum and maximum."""
    if feature.min is None and feature.max is None:
        return []

    below: list[tuple[int, Any]] = []
    above: list[tuple[int, Any]] = []
    for row, value in source.iter_values(feature.name):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if feature.min is not None and value < feature.min:
            below.append((row, value))
        if feature.max is not None and value > feature.max:
            above.append((row, value))

    found: list[Violation] = []
    if below:
        found.append(
            _bound_violation(feature, MLC203, "min", feature.min, below, settings, "below")
        )
    if above:
        found.append(
            _bound_violation(feature, MLC204, "max", feature.max, above, settings, "above")
        )
    return found


def _bound_violation(
    feature: Feature,
    code: ErrorCode,
    rule: str,
    bound: Any,
    offenders: list[tuple[int, Any]],
    settings: _Settings,
    direction: str,
) -> Violation:
    """Build the violation for a breached numeric bound."""
    worst = min(v for _, v in offenders) if direction == "below" else max(v for _, v in offenders)
    return Violation(
        code=code,
        severity=Severity.ERROR,
        message=f"Column {feature.name!r} has {len(offenders)} value(s) {direction} the "
        f"declared {rule} of {bound}; furthest is {worst}.",
        feature=feature.name,
        rule=rule,
        expected=bound,
        actual=worst,
        affected_rows=len(offenders),
        samples=settings.take(offenders),
        remediation=f"Clip or filter the offending rows, or relax {rule} if the data is "
        "legitimately wider than the contract assumed.",
    )


def _check_allowed_values(
    feature: Feature, source: DataSource, settings: _Settings
) -> list[Violation]:
    """Check values against the declared domain."""
    if feature.allowed_values is None:
        return []

    permitted = set(feature.allowed_values)
    offenders = [
        (row, value) for row, value in source.iter_values(feature.name) if value not in permitted
    ]
    if not offenders:
        return []

    unexpected = sorted({str(value) for _, value in offenders})
    return [
        Violation(
            code=MLC205,
            severity=Severity.ERROR,
            message=f"Column {feature.name!r} has {len(offenders)} value(s) outside the "
            f"allowed set. Unexpected: {', '.join(unexpected[:10])}.",
            feature=feature.name,
            rule="allowed_values",
            expected=list(feature.allowed_values),
            actual=unexpected,
            affected_rows=len(offenders),
            samples=settings.take(offenders),
            remediation="A new category upstream is the usual cause. Add it to "
            "allowed_values if legitimate, and bump the contract's minor version.",
        )
    ]


def _check_pattern(feature: Feature, source: DataSource, settings: _Settings) -> list[Violation]:
    """Check text values against the declared pattern.

    Uses full-match semantics: the pattern must describe the entire value, not
    merely occur somewhere inside it. For a contract that is the less surprising
    reading of "every value must match this pattern", and it means a pattern
    cannot accidentally pass because it matched a substring.
    """
    if feature.pattern is None:
        return []

    compiled = re.compile(feature.pattern)
    offenders = [
        (row, value)
        for row, value in source.iter_values(feature.name)
        if not (isinstance(value, str) and compiled.fullmatch(value))
    ]
    if not offenders:
        return []

    return [
        Violation(
            code=MLC206,
            severity=Severity.ERROR,
            message=f"Column {feature.name!r} has {len(offenders)} value(s) that do not match "
            f"the pattern {feature.pattern!r}.",
            feature=feature.name,
            rule="pattern",
            expected=feature.pattern,
            actual=None,
            affected_rows=len(offenders),
            samples=settings.take(offenders),
            remediation="Patterns match the whole value, not a substring. Check the pattern "
            "is anchored as you intend before assuming the data is wrong.",
        )
    ]


def _check_unique(feature: Feature, source: DataSource, settings: _Settings) -> list[Violation]:
    """Check that no value appears more than once."""
    if not feature.unique:
        return []

    counts = Counter(column_values(source, feature.name))
    repeated = {value for value, count in counts.items() if count > 1}
    if not repeated:
        return []

    offenders = [
        (row, value) for row, value in source.iter_values(feature.name) if value in repeated
    ]
    return [
        Violation(
            code=MLC207,
            severity=Severity.ERROR,
            message=f"Column {feature.name!r} is declared unique but has {len(repeated)} "
            f"duplicated value(s) across {len(offenders)} rows.",
            feature=feature.name,
            rule="unique",
            expected="all values distinct",
            actual=sorted(str(value) for value in repeated)[:10],
            affected_rows=len(offenders),
            samples=settings.take(offenders),
            remediation="Deduplicate upstream. Duplicate keys usually mean a join fanned out.",
        )
    ]
