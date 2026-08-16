"""Tests for the validation engine.

Exercised through the public API rather than against internal functions, so the
tests keep passing when the engine is refactored and start failing when
behaviour users depend on actually changes.
"""

from __future__ import annotations

from typing import Any

import pytest

from mlcontract import (
    Contract,
    ContractValidationError,
    DType,
    Feature,
    Severity,
    ValidationReport,
    validate,
)


def contract(*features: Feature, **overrides: Any) -> Contract:
    defaults: dict[str, Any] = {"name": "t", "version": "1.0.0", "features": features}
    return Contract(**{**defaults, **overrides})


def codes(report: ValidationReport) -> list[str]:
    return [v.code.code for v in report.violations]


class TestCleanData:
    def test_valid_data_produces_no_violations(self):
        report = contract(
            Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"]),
        ).validate([{"age": 30, "country": "IN"}, {"age": 41, "country": "US"}])

        assert report.is_valid
        assert report.violations == ()

    def test_report_carries_provenance(self):
        """A report archived from a CI run must still say what it checked."""
        report = contract(Feature("age", DType.INTEGER)).validate([{"age": 1}])
        assert report.contract_name == "t"
        assert report.contract_version == "1.0.0"
        assert report.row_count == 1
        assert "2 mappings" not in report.source


class TestStructure:
    def test_missing_required_column(self):
        report = contract(Feature("age", DType.INTEGER)).validate([{"other": 1}])
        assert "MLC101" in codes(report)
        assert not report.is_valid

    def test_missing_optional_column_is_fine(self):
        report = contract(
            Feature("age", DType.INTEGER, required=False),
            Feature("id", DType.INTEGER),
        ).validate([{"id": 1}])
        assert report.is_valid

    def test_extra_column_is_a_warning_when_allowed(self):
        """Undeclared columns surface upstream drift before it becomes failure."""
        report = contract(Feature("age", DType.INTEGER)).validate([{"age": 1, "extra": 2}])
        assert report.is_valid
        assert [v.severity for v in report.violations] == [Severity.WARNING]
        assert "MLC102" in codes(report)

    def test_extra_column_is_an_error_when_disallowed(self):
        report = contract(Feature("age", DType.INTEGER), allow_extra_columns=False).validate(
            [{"age": 1, "extra": 2}]
        )
        assert not report.is_valid
        assert "MLC102" in codes(report)

    def test_column_order_ignored_by_default(self):
        report = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER)).validate(
            [{"b": 1, "a": 2}]
        )
        assert report.is_valid

    def test_column_order_enforced_when_requested(self):
        report = contract(
            Feature("a", DType.INTEGER),
            Feature("b", DType.INTEGER),
            enforce_column_order=True,
        ).validate([{"b": 1, "a": 2}])
        assert "MLC103" in codes(report)

    def test_dtype_mismatch(self):
        report = contract(Feature("age", DType.INTEGER)).validate([{"age": "thirty"}])
        assert "MLC104" in codes(report)

    def test_integer_data_satisfies_a_float_contract(self):
        """Widening is safe: every integer is a valid float."""
        report = contract(Feature("x", DType.FLOAT)).validate([{"x": 1}, {"x": 2}])
        assert report.is_valid

    def test_float_data_fails_an_integer_contract(self):
        report = contract(Feature("x", DType.INTEGER)).validate([{"x": 1.5}])
        assert "MLC104" in codes(report)

    def test_booleans_are_not_integers(self):
        report = contract(Feature("x", DType.INTEGER)).validate([{"x": True}])
        assert "MLC104" in codes(report)

    def test_too_few_rows(self):
        report = contract(Feature("a", DType.INTEGER), min_rows=5).validate([{"a": 1}])
        assert "MLC105" in codes(report)

    def test_too_many_rows(self):
        report = contract(Feature("a", DType.INTEGER), max_rows=1).validate([{"a": 1}, {"a": 2}])
        assert "MLC106" in codes(report)

    def test_value_checks_are_skipped_after_a_type_failure(self):
        """A type failure must not cascade into every value rule also failing."""
        report = contract(Feature("age", DType.INTEGER, min=18, max=99)).validate(
            [{"age": "x"}, {"age": "y"}]
        )
        assert codes(report) == ["MLC104"]


class TestValues:
    def test_null_in_non_nullable(self):
        report = contract(Feature("age", DType.INTEGER, nullable=False)).validate(
            [{"age": 30}, {"age": None}]
        )
        assert "MLC201" in codes(report)

    def test_absent_key_counts_as_null(self):
        report = contract(Feature("age", DType.INTEGER, nullable=False)).validate([{"age": 30}, {}])
        assert "MLC201" in codes(report)

    def test_nulls_allowed_by_default(self):
        report = contract(Feature("age", DType.INTEGER)).validate([{"age": None}, {"age": 3}])
        assert report.is_valid

    def test_null_fraction_exceeded(self):
        report = contract(Feature("a", DType.INTEGER, max_null_fraction=0.25)).validate(
            [{"a": 1}, {"a": None}, {"a": None}, {"a": 4}]
        )
        assert "MLC202" in codes(report)

    def test_null_fraction_within_limit(self):
        report = contract(Feature("a", DType.INTEGER, max_null_fraction=0.5)).validate(
            [{"a": 1}, {"a": None}]
        )
        assert report.is_valid

    def test_below_min(self):
        report = contract(Feature("age", DType.INTEGER, min=18)).validate(
            [{"age": 30}, {"age": 12}]
        )
        assert "MLC203" in codes(report)

    def test_above_max(self):
        report = contract(Feature("age", DType.INTEGER, max=120)).validate([{"age": 500}])
        assert "MLC204" in codes(report)

    def test_bounds_are_inclusive(self):
        report = contract(Feature("age", DType.INTEGER, min=18, max=20)).validate(
            [{"age": 18}, {"age": 20}]
        )
        assert report.is_valid

    def test_value_outside_allowed_set(self):
        report = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"])).validate(
            [{"c": "IN"}, {"c": "FR"}]
        )
        assert "MLC205" in codes(report)

    def test_pattern_mismatch(self):
        report = contract(Feature("e", DType.STRING, pattern=r"^[^@]+@[^@]+$")).validate(
            [{"e": "a@b.com"}, {"e": "nope"}]
        )
        assert "MLC206" in codes(report)

    def test_duplicates_in_a_unique_feature(self):
        report = contract(Feature("id", DType.INTEGER, unique=True)).validate(
            [{"id": 1}, {"id": 2}, {"id": 1}]
        )
        assert "MLC207" in codes(report)

    def test_unique_feature_with_no_duplicates(self):
        report = contract(Feature("id", DType.INTEGER, unique=True)).validate(
            [{"id": 1}, {"id": 2}]
        )
        assert report.is_valid

    def test_nulls_do_not_count_as_duplicates(self):
        """Two missing values are not the same value repeated."""
        report = contract(Feature("id", DType.INTEGER, unique=True)).validate(
            [{"id": 1}, {"id": None}, {"id": None}]
        )
        assert report.is_valid

    def test_several_problems_reported_together(self):
        """The reason validation returns a report instead of raising."""
        report = contract(
            Feature("age", DType.INTEGER, nullable=False, min=18),
            Feature("c", DType.CATEGORICAL, allowed_values=["IN"]),
        ).validate([{"age": None, "c": "FR"}, {"age": 5, "c": "IN"}])
        assert set(codes(report)) == {"MLC201", "MLC203", "MLC205"}


class TestViolationDetail:
    def test_counts_all_affected_rows(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate(
            [{"a": -1}, {"a": -2}, {"a": 5}, {"a": -3}]
        )
        assert report.violations[0].affected_rows == 3

    def test_samples_point_at_real_rows(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": 5}, {"a": -7}])
        sample = report.violations[0].samples[0]
        assert sample.row == 1
        assert sample.value == -7

    def test_samples_are_capped(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate(
            [{"a": -i} for i in range(1, 50)], max_samples=3
        )
        assert len(report.violations[0].samples) == 3
        assert report.violations[0].affected_rows == 49

    def test_samples_can_be_suppressed(self):
        """Offending values are raw data, and reports do not always belong in it."""
        report = contract(Feature("email", DType.STRING, pattern=r"^x$")).validate(
            [{"email": "person@example.com"}], sample_values=False
        )
        assert report.violations[0].samples == ()
        assert report.violations[0].affected_rows == 1

    def test_violations_carry_remediation(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        assert report.violations[0].remediation


class TestReportApi:
    def test_errors_and_warnings_are_separable(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1, "extra": 1}])
        assert len(report.errors) == 1
        assert len(report.warnings) == 1

    def test_for_feature(self):
        report = contract(
            Feature("a", DType.INTEGER, min=0),
            Feature("b", DType.INTEGER, min=0),
        ).validate([{"a": -1, "b": -1}])
        assert len(report.for_feature("a")) == 1

    def test_codes_are_exposed_for_alerting(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        assert "MLC203" in report.codes()

    def test_to_dict_is_json_safe(self):
        import json

        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        json.dumps(report.to_dict())

    def test_to_json_round_trips(self):
        import json

        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        assert json.loads(report.to_json())["contract"]["name"] == "t"

    def test_summary_names_the_failing_feature(self):
        report = contract(Feature("age", DType.INTEGER, min=18)).validate([{"age": 1}])
        assert "age" in report.summary()

    def test_raise_for_status_is_silent_when_valid(self):
        contract(Feature("a", DType.INTEGER)).validate([{"a": 1}]).raise_for_status()

    def test_raise_for_status_raises_when_invalid(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        with pytest.raises(ContractValidationError) as exc:
            report.raise_for_status()
        assert exc.value.report is report

    def test_warnings_alone_do_not_raise(self):
        report = contract(Feature("a", DType.INTEGER)).validate([{"a": 1, "extra": 2}])
        report.raise_for_status()


class TestModuleLevelValidate:
    def test_equivalent_to_the_method(self):
        c = contract(Feature("a", DType.INTEGER, min=0))
        assert validate(c, [{"a": -1}]).to_dict() == c.validate([{"a": -1}]).to_dict()


class TestReportContainerBehaviour:
    def test_len_counts_every_violation(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1, "x": 1}])
        assert len(report) == 2

    def test_iteration_yields_violations(self):
        report = contract(Feature("a", DType.INTEGER, min=0)).validate([{"a": -1}])
        assert [v.code.code for v in report] == ["MLC203"]

    def test_no_truthiness_shortcut(self):
        """Truthiness is deliberately undefined: it could mean either opposite."""
        report = contract(Feature("a", DType.INTEGER)).validate([{"a": 1}])
        assert report.is_valid
        assert len(report) == 0

    def test_summary_says_so_when_clean(self):
        report = contract(Feature("a", DType.INTEGER)).validate([{"a": 1}])
        assert "PASSED" in report.summary()

    def test_violation_str_is_log_friendly(self):
        report = contract(Feature("age", DType.INTEGER, min=18)).validate([{"age": 1}])
        line = str(report.violations[0])
        assert line.startswith("MLC203")
        assert "[age]" in line

    def test_severity_str_is_the_wire_value(self):
        assert str(Severity.ERROR) == "error"
        assert str(Severity.WARNING) == "warning"


class TestEdgeCases:
    def test_column_order_matches_when_enforced(self):
        report = contract(
            Feature("a", DType.INTEGER),
            Feature("b", DType.INTEGER),
            enforce_column_order=True,
        ).validate([{"a": 1, "b": 2}])
        assert report.is_valid

    def test_ordering_ignores_undeclared_columns(self):
        """An extra column between two declared ones is not a reordering."""
        report = contract(
            Feature("a", DType.INTEGER),
            Feature("b", DType.INTEGER),
            enforce_column_order=True,
        ).validate([{"a": 1, "extra": 0, "b": 2}])
        assert "MLC103" not in codes(report)

    def test_range_check_ignores_non_numeric_values(self):
        """A mixed column already failed typing; range must not also explode."""
        report = contract(Feature("a", DType.FLOAT, min=0), allow_extra_columns=True).validate(
            [{"a": 1.0}, {"a": "x"}]
        )
        assert codes(report) == ["MLC104"]

    def test_pattern_passing_produces_no_violation(self):
        report = contract(Feature("e", DType.STRING, pattern=r"^\w+$")).validate(
            [{"e": "abc"}, {"e": "def"}]
        )
        assert report.is_valid


class TestBoundsIndependently:
    def test_only_max_declared(self):
        report = contract(Feature("a", DType.INTEGER, max=10)).validate([{"a": 5}, {"a": 50}])
        assert codes(report) == ["MLC204"]

    def test_only_min_declared(self):
        report = contract(Feature("a", DType.INTEGER, min=10)).validate([{"a": 5}, {"a": 50}])
        assert codes(report) == ["MLC203"]

    def test_both_bounds_violated_are_reported_separately(self):
        report = contract(Feature("a", DType.INTEGER, min=0, max=10)).validate(
            [{"a": -5}, {"a": 50}]
        )
        assert set(codes(report)) == {"MLC203", "MLC204"}

    def test_float_values_against_float_bounds(self):
        report = contract(Feature("a", DType.FLOAT, min=0.5)).validate([{"a": 0.25}])
        assert codes(report) == ["MLC203"]
