"""The result of validating data against a contract.

Validation returns a report rather than raising. That is a deliberate choice:
real datasets have several problems at once, and an exception carries only the
first one. A CI run should tell you all eight things wrong with today's extract,
not make you fix them one deploy at a time.

:meth:`ValidationReport.raise_for_status` is there for pipelines that genuinely
want to stop at the first sign of trouble.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from mlcontract.exceptions import ErrorCode


class Severity(Enum):
    """How much a violation matters.

    Errors make a report invalid. Warnings are surfaced but do not, so a
    condition can be visible without failing a build.
    """

    ERROR = "error"
    WARNING = "warning"

    def __str__(self) -> str:
        """Return the wire value."""
        return self.value


@dataclass(frozen=True, slots=True)
class Sample:
    """One offending value, with where it was found.

    Attributes:
        row: Zero-based position in the data.
        value: The value itself.
    """

    row: int
    value: Any

    def to_dict(self) -> dict[str, Any]:
        """Return the dictionary form."""
        return {"row": self.row, "value": self.value}


@dataclass(frozen=True, slots=True)
class Violation:
    """One way in which data failed to satisfy a contract.

    Every field exists to answer a question someone reading a failing CI log
    will ask: what broke, where, how badly, and what do I do about it.

    Attributes:
        code: The stable error code, for alerting and filtering.
        severity: Whether this invalidates the data or is merely notable.
        message: A complete human-readable description.
        feature: The feature involved, or None for contract-wide problems such
            as row counts.
        rule: The constraint that failed, for example ``"min"`` or ``"dtype"``.
        expected: What the contract required.
        actual: What the data had.
        affected_rows: How many rows violated the rule. None where the notion
            does not apply, as with column ordering.
        samples: Up to a handful of offending values, with row positions.
        remediation: A concrete suggestion for fixing it.
    """

    code: ErrorCode
    severity: Severity
    message: str
    feature: str | None = None
    rule: str | None = None
    expected: Any = None
    actual: Any = None
    affected_rows: int | None = None
    samples: tuple[Sample, ...] = ()
    remediation: str | None = None

    def __str__(self) -> str:
        """Return a single log-friendly line."""
        where = f" [{self.feature}]" if self.feature else ""
        return f"{self.code.code}{where} {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Return the dictionary form, omitting fields that were not set."""
        data: dict[str, Any] = {
            "code": self.code.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        for key, value in (
            ("feature", self.feature),
            ("rule", self.rule),
            ("expected", self.expected),
            ("actual", self.actual),
            ("affected_rows", self.affected_rows),
            ("remediation", self.remediation),
        ):
            if value is not None:
                data[key] = value
        if self.samples:
            data["samples"] = [sample.to_dict() for sample in self.samples]
        return data


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Everything that was wrong with the data, and enough context to act on it.

    Attributes:
        contract_name: The contract validated against.
        contract_version: Its version, so a report stays meaningful once
            archived.
        source: A short description of the data, for example ``"customers.csv"``.
        row_count: How many rows were examined.
        violations: Every violation found, errors and warnings together, in the
            order the engine produced them: contract-wide problems first, then
            per-feature in declaration order.
    """

    contract_name: str
    contract_version: str
    source: str
    row_count: int
    violations: tuple[Violation, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """Return True if nothing of error severity was found.

        Warnings do not make a report invalid — that is the point of having two
        severities.
        """
        return not self.errors

    @property
    def errors(self) -> tuple[Violation, ...]:
        """Return only the violations that invalidate the data."""
        return tuple(v for v in self.violations if v.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Violation, ...]:
        """Return only the violations that are notable but not disqualifying."""
        return tuple(v for v in self.violations if v.severity is Severity.WARNING)

    # Deliberately no __bool__. It would have to mean either "is valid" or "has
    # violations", and those are opposites — while __len__ below already implies
    # the second. One class cannot carry two contradictory truthiness stories, so
    # callers say `report.is_valid` and mean exactly that.

    def __len__(self) -> int:
        """Return the total number of violations, warnings included."""
        return len(self.violations)

    def __iter__(self) -> Any:
        """Iterate over every violation."""
        return iter(self.violations)

    def for_feature(self, name: str) -> tuple[Violation, ...]:
        """Return the violations concerning one feature."""
        return tuple(v for v in self.violations if v.feature == name)

    def codes(self) -> tuple[str, ...]:
        """Return the error codes present, in order and without duplicates.

        Convenient for assertions and for alerting rules that care which kinds
        of problem occurred rather than how many.
        """
        seen: list[str] = []
        for violation in self.violations:
            if violation.code.code not in seen:
                seen.append(violation.code.code)
        return tuple(seen)

    def summary(self) -> str:
        """Return a human-readable multi-line summary.

        Written for someone scanning a CI log: the verdict first, then each
        problem with its code, location and a sample of offending values.
        """
        header = (
            f"{self.contract_name} v{self.contract_version} against {self.source} "
            f"({self.row_count} rows)"
        )
        if not self.violations:
            return f"{header}\nPASSED: no violations."

        verdict = "PASSED with warnings" if self.is_valid else "FAILED"
        counts = f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        lines = [header, f"{verdict}: {counts}", ""]

        for violation in self.violations:
            marker = "ERROR  " if violation.severity is Severity.ERROR else "WARNING"
            where = f" {violation.feature}:" if violation.feature else ""
            lines.append(f"  {marker} {violation.code.code}{where} {violation.message}")
            if violation.samples:
                shown = ", ".join(f"row {s.row}={s.value!r}" for s in violation.samples)
                lines.append(f"          e.g. {shown}")
            if violation.remediation:
                lines.append(f"          fix: {violation.remediation}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return the machine-readable form.

        Deliberately free of timestamps and other run-specific values, so two
        validations of the same data produce byte-identical output and reports
        can be diffed or used as test fixtures.
        """
        return {
            "contract": {"name": self.contract_name, "version": self.contract_version},
            "source": self.source,
            "row_count": self.row_count,
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "violations": [violation.to_dict() for violation in self.violations],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Return the machine-readable form as JSON text."""
        from mlcontract.serialization import encode_json

        return encode_json(self.to_dict(), indent=indent)

    def raise_for_status(self) -> None:
        """Raise if the data is invalid, for pipelines that want to fail fast.

        Raises:
            ContractValidationError: If any error-severity violation was found.
                The exception carries the full report on its ``report``
                attribute, so nothing is lost by catching it.
        """
        if self.is_valid:
            return

        from mlcontract.exceptions import ContractValidationError

        first = self.errors[0]
        raise ContractValidationError(
            f"{self.contract_name} v{self.contract_version}: {len(self.errors)} violation(s). "
            f"First: {first}",
            code=first.code,
            report=self,
            contract=self.contract_name,
            violations=len(self.errors),
        )
