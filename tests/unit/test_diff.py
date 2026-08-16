"""Tests for contract diffing and compatibility.

The classification table is the load-bearing claim of this library: if it is
wrong, the tool confidently tells people a breaking change is safe. So every row
of it gets a named test, in both directions, rather than a sample of the obvious
cases.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from mlcontract import (
    ChangeKind,
    Compatibility,
    CompatibilityError,
    Contract,
    DType,
    Feature,
    Impact,
    VersionBump,
)


def contract(*features: Feature, version: str = "1.0.0", **overrides: Any) -> Contract:
    defaults: dict[str, Any] = {"name": "c", "version": version, "features": features}
    return Contract(**{**defaults, **overrides})


def impacts(old: Contract, new: Contract) -> list[Impact]:
    return [change.impact for change in old.diff(new)]


def only_impact(old: Contract, new: Contract) -> Impact:
    """Assert exactly one change and return its impact."""
    found = list(old.diff(new))
    assert len(found) == 1, f"expected one change, got {[str(c) for c in found]}"
    return found[0].impact


class TestNoChange:
    def test_identical_contracts_have_no_differences(self):
        c = contract(Feature("a", DType.INTEGER, min=0))
        assert c.diff(c).is_empty

    def test_diff_with_itself_is_never_breaking(self):
        c = contract(Feature("a", DType.INTEGER, min=0, unique=True))
        assert not c.diff(c).is_breaking

    def test_required_bump_is_none(self):
        c = contract(Feature("a", DType.INTEGER))
        assert c.diff(c).required_bump is VersionBump.NONE


class TestFeatureAddedAndRemoved:
    def test_required_feature_added_is_breaking(self):
        """Data written for the old contract has no such column."""
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_optional_feature_added_is_safe(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER, required=False))
        assert only_impact(old, new) is Impact.RELAXED

    def test_feature_removed_is_backward_safe(self):
        """Dropping a declaration cannot reject data that previously passed."""
        old = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER))
        assert only_impact(old, new) is Impact.RELAXED

    def test_removal_is_reported_with_the_right_kind(self):
        old = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER))
        assert next(iter(old.diff(new))).kind is ChangeKind.FEATURE_REMOVED


class TestDtypeChanges:
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (DType.INTEGER, DType.FLOAT),
            (DType.CATEGORICAL, DType.STRING),
            (DType.DATE, DType.DATETIME),
        ],
    )
    def test_widening_is_safe(self, before, after):
        old = contract(Feature("a", before))
        new = contract(Feature("a", after))
        assert only_impact(old, new) is Impact.RELAXED

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (DType.FLOAT, DType.INTEGER),
            (DType.STRING, DType.CATEGORICAL),
            (DType.DATETIME, DType.DATE),
            (DType.INTEGER, DType.STRING),
        ],
    )
    def test_narrowing_is_breaking(self, before, after):
        old = contract(Feature("a", before))
        new = contract(Feature("a", after))
        assert only_impact(old, new) is Impact.TIGHTENED


class TestNullabilityAndRequirement:
    def test_making_a_feature_non_nullable_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER, nullable=True))
        new = contract(Feature("a", DType.INTEGER, nullable=False))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_making_a_feature_nullable_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, nullable=False))
        new = contract(Feature("a", DType.INTEGER, nullable=True))
        assert only_impact(old, new) is Impact.RELAXED

    def test_making_a_feature_required_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER, required=False))
        new = contract(Feature("a", DType.INTEGER, required=True))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_making_a_feature_optional_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, required=True))
        new = contract(Feature("a", DType.INTEGER, required=False))
        assert only_impact(old, new) is Impact.RELAXED


class TestNumericBounds:
    def test_raising_min_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_lowering_min_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, min=18))
        new = contract(Feature("a", DType.INTEGER, min=0))
        assert only_impact(old, new) is Impact.RELAXED

    def test_lowering_max_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER, max=100))
        new = contract(Feature("a", DType.INTEGER, max=10))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_raising_max_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, max=10))
        new = contract(Feature("a", DType.INTEGER, max=100))
        assert only_impact(old, new) is Impact.RELAXED

    def test_adding_a_bound_is_breaking(self):
        """An absent constraint accepts everything, so adding one can only reject."""
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER, min=0))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_removing_a_bound_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER))
        assert only_impact(old, new) is Impact.RELAXED

    def test_min_of_zero_is_not_mistaken_for_absent(self):
        """0 == False in Python, which is how zero-valued constraints get lost."""
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER, min=0))
        assert only_impact(old, new) is Impact.TIGHTENED


class TestAllowedValues:
    def test_removing_a_category_is_breaking(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_adding_a_category_is_safe(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        assert only_impact(old, new) is Impact.RELAXED

    def test_swapping_categories_is_breaking(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["US"]))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_reordering_categories_is_not_a_change(self):
        """The set is what matters, not the order it was written in."""
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["US", "IN"]))
        assert old.diff(new).is_empty

    def test_the_description_names_what_was_removed(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN"]))
        assert "US" in next(iter(old.diff(new))).description


class TestPatternAndUniqueness:
    def test_adding_a_pattern_is_breaking(self):
        old = contract(Feature("s", DType.STRING))
        new = contract(Feature("s", DType.STRING, pattern=r"^\d+$"))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_removing_a_pattern_is_safe(self):
        old = contract(Feature("s", DType.STRING, pattern=r"^\d+$"))
        new = contract(Feature("s", DType.STRING))
        assert only_impact(old, new) is Impact.RELAXED

    def test_changing_a_pattern_is_treated_as_breaking(self):
        """Regex containment is undecidable, so the conservative answer is honest."""
        old = contract(Feature("s", DType.STRING, pattern=r"^\d+$"))
        new = contract(Feature("s", DType.STRING, pattern=r"^\d{2}$"))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_requiring_uniqueness_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER, unique=True))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_dropping_uniqueness_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, unique=True))
        new = contract(Feature("a", DType.INTEGER))
        assert only_impact(old, new) is Impact.RELAXED


class TestNullFraction:
    def test_lowering_the_permitted_fraction_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER, max_null_fraction=0.5))
        new = contract(Feature("a", DType.INTEGER, max_null_fraction=0.1))
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_raising_the_permitted_fraction_is_safe(self):
        old = contract(Feature("a", DType.INTEGER, max_null_fraction=0.1))
        new = contract(Feature("a", DType.INTEGER, max_null_fraction=0.5))
        assert only_impact(old, new) is Impact.RELAXED


class TestContractSettings:
    def test_enforcing_column_order_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), enforce_column_order=True)
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_relaxing_column_order_is_safe(self):
        old = contract(Feature("a", DType.INTEGER), enforce_column_order=True)
        new = contract(Feature("a", DType.INTEGER))
        assert only_impact(old, new) is Impact.RELAXED

    def test_forbidding_extra_columns_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), allow_extra_columns=False)
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_raising_min_rows_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER), min_rows=1)
        new = contract(Feature("a", DType.INTEGER), min_rows=100)
        assert only_impact(old, new) is Impact.TIGHTENED

    def test_lowering_max_rows_is_breaking(self):
        old = contract(Feature("a", DType.INTEGER), max_rows=1000)
        new = contract(Feature("a", DType.INTEGER), max_rows=10)
        assert only_impact(old, new) is Impact.TIGHTENED


class TestNeutralChanges:
    def test_description_change_is_neutral(self):
        old = contract(Feature("a", DType.INTEGER, description="before"))
        new = contract(Feature("a", DType.INTEGER, description="after"))
        assert only_impact(old, new) is Impact.NEUTRAL

    def test_contract_description_change_is_neutral(self):
        old = contract(Feature("a", DType.INTEGER), description="before")
        new = contract(Feature("a", DType.INTEGER), description="after")
        assert only_impact(old, new) is Impact.NEUTRAL

    def test_metadata_change_is_neutral(self):
        old = contract(Feature("a", DType.INTEGER), metadata={"team": "risk"})
        new = contract(Feature("a", DType.INTEGER), metadata={"team": "fraud"})
        assert only_impact(old, new) is Impact.NEUTRAL

    def test_neutral_changes_are_not_breaking(self):
        old = contract(Feature("a", DType.INTEGER), description="before")
        new = contract(Feature("a", DType.INTEGER), description="after")
        assert not old.diff(new).is_breaking


class TestRenames:
    def test_a_declared_rename_is_reported_once(self):
        """Not as an unrelated removal plus addition."""
        old = contract(Feature("age", DType.INTEGER))
        new = contract(Feature("customer_age", DType.INTEGER, previous_names=["age"]))
        changes = list(old.diff(new))
        assert [c.kind for c in changes] == [ChangeKind.FEATURE_RENAMED]

    def test_a_rename_is_breaking(self):
        """Existing data still carries the old column name."""
        old = contract(Feature("age", DType.INTEGER))
        new = contract(Feature("customer_age", DType.INTEGER, previous_names=["age"]))
        assert old.diff(new).is_breaking

    def test_an_undeclared_rename_is_a_removal_and_an_addition(self):
        """Guessing a rename would be a confident wrong answer."""
        old = contract(Feature("age", DType.INTEGER))
        new = contract(Feature("customer_age", DType.INTEGER))
        kinds = {c.kind for c in old.diff(new)}
        assert kinds == {ChangeKind.FEATURE_ADDED, ChangeKind.FEATURE_REMOVED}

    def test_constraints_are_still_compared_across_a_rename(self):
        old = contract(Feature("age", DType.INTEGER, min=0))
        new = contract(Feature("customer_age", DType.INTEGER, min=18, previous_names=["age"]))
        kinds = [c.kind for c in old.diff(new)]
        assert ChangeKind.CONSTRAINT_CHANGED in kinds

    def test_previous_names_pointing_nowhere_are_ignored(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER, previous_names=["never_existed"]))
        assert old.diff(new).is_empty


class TestVersionBump:
    def test_breaking_requires_major(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18), version="1.0.1")
        assert old.diff(new).required_bump is VersionBump.MAJOR

    def test_relaxing_requires_minor(self):
        old = contract(Feature("a", DType.INTEGER, min=18))
        new = contract(Feature("a", DType.INTEGER, min=0), version="1.1.0")
        assert old.diff(new).required_bump is VersionBump.MINOR

    def test_cosmetic_requires_patch(self):
        old = contract(Feature("a", DType.INTEGER, description="x"))
        new = contract(Feature("a", DType.INTEGER, description="y"), version="1.0.1")
        assert old.diff(new).required_bump is VersionBump.PATCH

    def test_the_highest_requirement_wins(self):
        old = contract(Feature("a", DType.INTEGER, min=0, description="x"))
        new = contract(Feature("a", DType.INTEGER, min=18, description="y"), version="2.0.0")
        assert old.diff(new).required_bump is VersionBump.MAJOR

    @pytest.mark.parametrize(
        ("before", "after", "expected"),
        [
            ("1.0.0", "2.0.0", VersionBump.MAJOR),
            ("1.0.0", "1.1.0", VersionBump.MINOR),
            ("1.0.0", "1.0.1", VersionBump.PATCH),
            ("1.0.0", "1.0.0", VersionBump.NONE),
            ("1.0.0", "2.0.0-rc.1", VersionBump.MAJOR),
            ("1.0.0", "1.0.1+build.7", VersionBump.PATCH),
        ],
    )
    def test_declared_bump_is_read_from_the_versions(self, before, after, expected):
        old = contract(Feature("a", DType.INTEGER), version=before)
        new = contract(Feature("a", DType.INTEGER), version=after)
        assert old.diff(new).declared_bump is expected

    def test_insufficient_bump_is_detected(self):
        """The check worth putting in CI: a breaking change shipped as a patch."""
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18), version="1.0.1")
        assert not old.diff(new).is_version_bump_sufficient

    def test_sufficient_bump_is_accepted(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18), version="2.0.0")
        assert old.diff(new).is_version_bump_sufficient

    def test_a_larger_bump_than_needed_is_fine(self):
        old = contract(Feature("a", DType.INTEGER, description="x"))
        new = contract(Feature("a", DType.INTEGER, description="y"), version="2.0.0")
        assert old.diff(new).is_version_bump_sufficient

    def test_the_warning_appears_in_the_summary(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18), version="1.0.1")
        assert "require a major bump" in old.diff(new).summary()


class TestDirectionalCompatibility:
    def test_adding_a_required_field_breaks_backward_not_forward(self):
        """It breaks producers, not consumers — which a single boolean cannot say."""
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))

        assert not old.is_compatible_with(new, Compatibility.BACKWARD).is_compatible
        assert old.is_compatible_with(new, Compatibility.FORWARD).is_compatible

    def test_removing_a_required_field_breaks_forward_not_backward(self):
        """The exact mirror image."""
        old = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER))

        assert old.is_compatible_with(new, Compatibility.BACKWARD).is_compatible
        assert not old.is_compatible_with(new, Compatibility.FORWARD).is_compatible

    def test_full_requires_both(self):
        old = contract(Feature("a", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        assert not old.is_compatible_with(new, Compatibility.FULL).is_compatible

    def test_a_purely_cosmetic_change_is_compatible_in_every_direction(self):
        old = contract(Feature("a", DType.INTEGER, description="x"))
        new = contract(Feature("a", DType.INTEGER, description="y"))
        for mode in Compatibility:
            assert old.is_compatible_with(new, mode).is_compatible

    def test_relaxing_a_bound_breaks_forward_only(self):
        """Old consumers cannot read data the widened contract now permits."""
        old = contract(Feature("a", DType.INTEGER, min=18))
        new = contract(Feature("a", DType.INTEGER, min=0))
        assert old.is_compatible_with(new, Compatibility.BACKWARD).is_compatible
        assert not old.is_compatible_with(new, Compatibility.FORWARD).is_compatible

    def test_mode_accepts_a_string(self):
        old = contract(Feature("a", DType.INTEGER))
        assert old.is_compatible_with(old, "full").is_compatible

    def test_backward_is_the_default(self):
        old = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER))
        assert old.is_compatible_with(new).mode is Compatibility.BACKWARD

    def test_the_result_names_the_offending_changes(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        result = old.is_compatible_with(new)
        assert len(result.breaking_changes) == 1
        assert result.breaking_changes[0].attribute == "min"


class TestCompatibilityResultApi:
    def test_raise_for_status_is_silent_when_compatible(self):
        c = contract(Feature("a", DType.INTEGER))
        c.is_compatible_with(c).raise_for_status()

    def test_raise_for_status_raises_when_incompatible(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        result = old.is_compatible_with(new)
        with pytest.raises(CompatibilityError) as exc:
            result.raise_for_status()
        assert exc.value.code.code == "MLC601"
        assert exc.value.result is result

    def test_summary_when_compatible(self):
        c = contract(Feature("a", DType.INTEGER))
        assert "COMPATIBLE" in c.is_compatible_with(c).summary()

    def test_summary_names_both_directions(self):
        old = contract(Feature("a", DType.INTEGER), Feature("b", DType.INTEGER))
        new = contract(Feature("a", DType.INTEGER), Feature("c", DType.INTEGER))
        text = old.is_compatible_with(new, Compatibility.FULL).summary()
        assert "cannot read data written for the old one" in text
        assert "cannot read data written for the new one" in text

    def test_to_dict_is_json_safe(self):
        import json

        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN"]))
        json.dumps(old.is_compatible_with(new).to_dict())

    def test_to_json(self):
        import json

        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        assert json.loads(old.is_compatible_with(new).to_json())["compatible"] is False


class TestDiffApi:
    def test_len_and_iteration(self):
        old = contract(Feature("a", DType.INTEGER, min=0, max=10))
        new = contract(Feature("a", DType.INTEGER, min=5, max=20))
        changes = old.diff(new)
        assert len(changes) == 2
        assert len(list(changes)) == 2

    def test_change_str_is_log_friendly(self):
        old = contract(Feature("age", DType.INTEGER, min=0))
        new = contract(Feature("age", DType.INTEGER, min=18))
        assert "age" in str(next(iter(old.diff(new))))

    def test_summary_when_identical(self):
        c = contract(Feature("a", DType.INTEGER))
        assert "No differences" in c.diff(c).summary()

    def test_to_dict_is_json_safe(self):
        import json

        old = contract(Feature("a", DType.INTEGER), metadata={"x": [1, 2]})
        new = contract(Feature("a", DType.FLOAT), metadata={"x": [3]})
        json.dumps(old.diff(new).to_dict())

    def test_to_json_reports_the_required_bump(self):
        import json

        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        assert json.loads(old.diff(new).to_json())["required_bump"] == "major"

    def test_changes_expose_before_and_after(self):
        old = contract(Feature("a", DType.INTEGER, min=0))
        new = contract(Feature("a", DType.INTEGER, min=18))
        change = next(iter(old.diff(new)))
        assert (change.before, change.after) == (0, 18)


class TestDualityInvariant:
    """Forward compatibility must equal backward compatibility, reversed."""

    CASES: ClassVar[list[tuple[Feature, Feature]]] = [
        (Feature("a", DType.INTEGER, min=0), Feature("a", DType.INTEGER, min=18)),
        (Feature("a", DType.FLOAT), Feature("a", DType.INTEGER)),
        (Feature("a", DType.INTEGER, nullable=True), Feature("a", DType.INTEGER, nullable=False)),
        (Feature("a", DType.STRING), Feature("a", DType.STRING, pattern="^x$")),
        (Feature("a", DType.INTEGER), Feature("a", DType.INTEGER, unique=True)),
    ]

    @pytest.mark.parametrize(("before", "after"), CASES)
    def test_forward_equals_reversed_backward(self, before, after):
        old, new = contract(before), contract(after)
        forward = old.is_compatible_with(new, Compatibility.FORWARD)
        reversed_backward = new.is_compatible_with(old, Compatibility.BACKWARD)
        assert forward.is_compatible == reversed_backward.is_compatible

    @pytest.mark.parametrize(("before", "after"), CASES)
    def test_a_tightening_change_reverses_to_a_relaxing_one(self, before, after):
        old, new = contract(before), contract(after)
        assert impacts(old, new) == [Impact.TIGHTENED]
        assert impacts(new, old) == [Impact.RELAXED]


class TestAllowedValuesOrdering:
    """Reordering must be a no-op, or contract reformats churn every check."""

    def test_reordering_is_not_a_change(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["UK", "IN", "US"]))
        assert old.diff(new).is_empty

    def test_reordering_stays_compatible_in_every_direction(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["US", "IN"]))
        for mode in Compatibility:
            assert old.is_compatible_with(new, mode).is_compatible

    def test_reordering_plus_an_addition_is_still_a_relaxation(self):
        old = contract(Feature("c", DType.CATEGORICAL, allowed_values=["IN", "US"]))
        new = contract(Feature("c", DType.CATEGORICAL, allowed_values=["US", "IN", "UK"]))
        assert only_impact(old, new) is Impact.RELAXED


class TestEnumWireValues:
    """Enum values appear in JSON output, so they are part of the interface."""

    def test_change_kind(self):
        assert str(ChangeKind.FEATURE_ADDED) == "feature_added"

    def test_impact(self):
        assert str(Impact.TIGHTENED) == "tightened"

    def test_version_bump(self):
        assert str(VersionBump.MAJOR) == "major"

    def test_compatibility(self):
        assert str(Compatibility.BACKWARD) == "backward"
