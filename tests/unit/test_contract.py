"""Tests for the Contract and Feature domain model."""

from __future__ import annotations

from typing import Any

import pytest

from schemapact import Contract, ContractDefinitionError, DType, Feature


def make_contract(**overrides: Any) -> Contract:
    defaults: dict[str, Any] = {
        "name": "customer_features",
        "version": "1.0.0",
        "features": [
            Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
            Feature("income", DType.FLOAT, min=0),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
        ],
    }
    return Contract(**{**defaults, **overrides})


class TestFeatureConstruction:
    def test_minimal(self):
        feature = Feature("age", DType.INTEGER)
        assert feature.name == "age"
        assert feature.dtype is DType.INTEGER
        assert feature.nullable is True
        assert feature.required is True

    def test_dtype_alias_is_normalised(self):
        assert Feature("age", "int64").dtype is DType.INTEGER  # type: ignore[arg-type]

    def test_allowed_values_become_a_tuple(self):
        """Lists are what users write; tuples are what immutability requires."""
        feature = Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"])
        assert feature.allowed_values == ("IN", "US")

    def test_previous_names_become_a_tuple(self):
        feature = Feature("age", DType.INTEGER, previous_names=["customer_age"])
        assert feature.previous_names == ("customer_age",)

    def test_is_immutable(self):
        feature = Feature("age", DType.INTEGER)
        with pytest.raises(AttributeError):
            feature.name = "other"  # type: ignore[misc]

    def test_equality_is_by_value(self):
        assert Feature("age", DType.INTEGER, min=0) == Feature("age", DType.INTEGER, min=0)
        assert Feature("age", DType.INTEGER) != Feature("age", DType.FLOAT)

    def test_repr_names_the_identifying_fields(self):
        assert repr(Feature("age", DType.INTEGER)) == (
            "Feature(name='age', dtype=integer, required=True, nullable=False)".replace(
                "nullable=False", "nullable=True"
            )
        )


class TestFeatureValidation:
    @pytest.mark.parametrize("name", ["", "   ", None, 42])
    def test_bad_names_rejected(self, name):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature(name, DType.INTEGER)
        assert exc.value.code.code == "SPX001"

    def test_min_above_max(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, min=100, max=10)
        assert exc.value.code.code == "SPX009"
        assert "no value could ever satisfy" in str(exc.value)

    def test_equal_bounds_allowed(self):
        assert Feature("constant", DType.INTEGER, min=5, max=5).min == 5

    def test_non_numeric_bound(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, min="eighteen")  # type: ignore[arg-type]
        assert exc.value.code.code == "SPX007"

    def test_range_on_text_type_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("name", DType.STRING, min=0)
        assert exc.value.code.code == "SPX008"
        assert "cannot use the 'min' constraint" in str(exc.value)

    def test_pattern_on_numeric_type_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, pattern=r"\d+")
        assert exc.value.code.code == "SPX008"

    def test_invalid_regex(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("email", DType.STRING, pattern="[unclosed")
        assert exc.value.code.code == "SPX007"

    def test_empty_allowed_values(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("country", DType.CATEGORICAL, allowed_values=[])
        assert exc.value.code.code == "SPX007"

    def test_duplicate_allowed_values(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "IN"])
        assert exc.value.code.code == "SPX007"

    def test_allowed_values_must_match_dtype(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("count", DType.INTEGER, allowed_values=[1, "two"])
        assert exc.value.code.code == "SPX007"

    def test_booleans_are_not_integers(self):
        """``bool`` subclasses ``int`` in Python; a contract must not conflate them."""
        with pytest.raises(ContractDefinitionError):
            Feature("count", DType.INTEGER, allowed_values=[True])

    @pytest.mark.parametrize("value", [-0.1, 1.5, "half", True])
    def test_bad_null_fraction(self, value):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, max_null_fraction=value)
        assert exc.value.code.code == "SPX007"

    def test_null_fraction_contradicts_non_nullable(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, nullable=False, max_null_fraction=0.1)
        assert exc.value.code.code == "SPX009"

    def test_zero_null_fraction_on_non_nullable_is_consistent(self):
        feature = Feature("age", DType.INTEGER, nullable=False, max_null_fraction=0.0)
        assert feature.max_null_fraction == 0.0

    def test_previous_names_cannot_include_own_name(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, previous_names=["age"])
        assert exc.value.code.code == "SPX013"

    def test_previous_names_cannot_repeat(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("age", DType.INTEGER, previous_names=["a", "a"])
        assert exc.value.code.code == "SPX013"


class TestContractConstruction:
    def test_feature_order_is_preserved(self):
        assert make_contract().feature_names == ("age", "income", "country")

    def test_features_become_a_tuple(self):
        assert isinstance(make_contract().features, tuple)

    def test_is_immutable(self):
        with pytest.raises(AttributeError):
            make_contract().name = "other"  # type: ignore[misc]

    def test_metadata_is_copied_not_aliased(self):
        source = {"team": "risk"}
        contract = make_contract(metadata=source)
        source["team"] = "fraud"
        assert contract.metadata == {"team": "risk"}

    def test_equality_is_by_value(self):
        assert make_contract() == make_contract()
        assert make_contract() != make_contract(version="2.0.0")


class TestContractAccess:
    def test_len(self):
        assert len(make_contract()) == 3

    def test_iteration_yields_features_in_order(self):
        assert [f.name for f in make_contract()] == ["age", "income", "country"]

    def test_membership(self):
        contract = make_contract()
        assert "age" in contract
        assert "missing" not in contract

    def test_getitem(self):
        assert make_contract()["age"].dtype is DType.INTEGER

    def test_getitem_missing_raises_keyerror(self):
        with pytest.raises(KeyError, match="no feature named"):
            make_contract()["missing"]

    def test_get_returns_none_when_absent(self):
        assert make_contract().get("missing") is None

    def test_required_features(self):
        contract = make_contract(
            features=[
                Feature("a", DType.INTEGER),
                Feature("b", DType.INTEGER, required=False),
            ]
        )
        assert [f.name for f in contract.required_features] == ["a"]

    def test_repr(self):
        assert repr(make_contract()) == (
            "Contract(name='customer_features', version='1.0.0', features=3)"
        )


class TestContractValidation:
    @pytest.mark.parametrize("name", ["", "  ", None, 7])
    def test_bad_names_rejected(self, name):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(name=name)
        assert exc.value.code.code == "SPX001"

    @pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0.0", "", None, "01.0.0"])
    def test_invalid_versions_rejected(self, version):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(version=version)
        assert exc.value.code.code == "SPX004"

    @pytest.mark.parametrize("version", ["0.1.0", "1.2.3", "1.0.0-alpha.1", "1.0.0+build.5"])
    def test_valid_versions_accepted(self, version):
        assert make_contract(version=version).version == version

    def test_no_features_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(features=[])
        assert exc.value.code.code == "SPX012"

    def test_duplicate_feature_names_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(features=[Feature("age", DType.INTEGER), Feature("age", DType.FLOAT)])
        assert exc.value.code.code == "SPX005"

    def test_non_feature_entries_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(features=[{"name": "age"}])
        assert exc.value.code.code == "SPX010"

    def test_rename_cannot_target_a_live_feature(self):
        """If both names still exist, it is not a rename — it is two features."""
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(
                features=[
                    Feature("age", DType.INTEGER),
                    Feature("customer_age", DType.INTEGER, previous_names=["age"]),
                ]
            )
        assert exc.value.code.code == "SPX013"

    @pytest.mark.parametrize("bound", ["min_rows", "max_rows"])
    @pytest.mark.parametrize("value", [-1, 1.5, "many", True])
    def test_bad_row_bounds(self, bound, value):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(**{bound: value})
        assert exc.value.code.code == "SPX014"

    def test_min_rows_above_max_rows(self):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(min_rows=100, max_rows=10)
        assert exc.value.code.code == "SPX014"

    def test_zero_row_bounds_allowed(self):
        assert make_contract(min_rows=0, max_rows=0).min_rows == 0

    def test_unsupported_spec_version(self):
        with pytest.raises(ContractDefinitionError) as exc:
            make_contract(spec_version="99")
        assert exc.value.code.code == "SPX003"
        assert "Upgrade schemapact" in str(exc.value)


class TestZeroValuedConstraints:
    """Regression tests for zero being confused with an undeclared constraint.

    ``value in (None, False)`` looks like a reasonable "is this set?" check, but
    ``0 == False`` in Python, so it silently discards every zero-valued
    constraint. That dropped ``min=0`` from serialised contracts and skipped its
    validation. Found by the property tests; pinned here so it cannot return.
    """

    def test_min_zero_survives_serialisation(self):
        contract = make_contract(features=[Feature("income", DType.FLOAT, min=0)])
        assert Contract.from_dict(contract.to_dict())["income"].min == 0

    def test_max_zero_survives_serialisation(self):
        contract = make_contract(features=[Feature("debt", DType.FLOAT, max=0)])
        assert Contract.from_dict(contract.to_dict())["debt"].max == 0

    def test_zero_null_fraction_survives_serialisation(self):
        contract = make_contract(features=[Feature("age", DType.INTEGER, max_null_fraction=0.0)])
        assert Contract.from_dict(contract.to_dict())["age"].max_null_fraction == 0.0

    def test_min_zero_is_written_to_the_document(self):
        contract = make_contract(features=[Feature("income", DType.FLOAT, min=0)])
        assert contract.to_dict()["features"]["income"]["min"] == 0

    def test_zero_bound_still_checked_for_applicability(self):
        """The same bug let a numeric-only constraint through on a text type."""
        with pytest.raises(ContractDefinitionError) as exc:
            Feature("name", DType.STRING, min=0)
        assert exc.value.code.code == "SPX008"

    def test_unique_false_remains_undeclared(self):
        """``unique=False`` is the default and must stay out of the document."""
        contract = make_contract(features=[Feature("a", DType.INTEGER, unique=False)])
        assert "unique" not in contract.to_dict()["features"]["a"]
