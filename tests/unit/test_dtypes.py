"""Tests for the canonical type system."""

from __future__ import annotations

import pytest

from schemapact import DType
from schemapact.exceptions import ContractDefinitionError


class TestParsing:
    def test_canonical_names_resolve(self):
        for member in DType:
            assert DType.parse(member.value) is member

    def test_dtype_passes_through(self):
        assert DType.parse(DType.FLOAT) is DType.FLOAT

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            ("int", DType.INTEGER),
            ("int64", DType.INTEGER),
            ("INT64", DType.INTEGER),
            ("  float64  ", DType.FLOAT),
            ("double", DType.FLOAT),
            ("bool", DType.BOOLEAN),
            ("str", DType.STRING),
            ("category", DType.CATEGORICAL),
            ("timestamp", DType.DATETIME),
        ],
    )
    def test_aliases(self, alias, expected):
        assert DType.parse(alias) is expected

    def test_unknown_name_lists_alternatives(self):
        with pytest.raises(ContractDefinitionError) as exc:
            DType.parse("complex128")
        assert exc.value.code.code == "SPX006"
        assert "integer" in str(exc.value)

    def test_object_is_not_an_alias(self):
        """Pandas' ``object`` means "anything at all", so it must not alias to string."""
        with pytest.raises(ContractDefinitionError):
            DType.parse("object")

    def test_non_string_rejected(self):
        with pytest.raises(ContractDefinitionError) as exc:
            DType.parse(42)  # type: ignore[arg-type]
        assert exc.value.code.code == "SPX006"


class TestProperties:
    def test_numeric(self):
        assert DType.INTEGER.is_numeric
        assert DType.FLOAT.is_numeric
        assert not DType.STRING.is_numeric
        assert not DType.BOOLEAN.is_numeric

    def test_temporal(self):
        assert DType.DATE.is_temporal
        assert DType.DATETIME.is_temporal
        assert not DType.INTEGER.is_temporal

    def test_textual(self):
        assert DType.STRING.is_textual
        assert DType.CATEGORICAL.is_textual
        assert not DType.FLOAT.is_textual

    def test_str_is_the_wire_value(self):
        """Enum string behaviour shifted between 3.10 and 3.12; ours must not."""
        assert str(DType.INTEGER) == "integer"
        assert f"{DType.CATEGORICAL}" == "categorical"


class TestWidening:
    def test_reflexive(self):
        for member in DType:
            assert member.widens_to(member)

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (DType.INTEGER, DType.FLOAT),
            (DType.CATEGORICAL, DType.STRING),
            (DType.DATE, DType.DATETIME),
        ],
    )
    def test_permitted_widenings(self, source, target):
        assert source.widens_to(target)

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (DType.FLOAT, DType.INTEGER),
            (DType.STRING, DType.CATEGORICAL),
            (DType.DATETIME, DType.DATE),
            (DType.INTEGER, DType.STRING),
            (DType.BOOLEAN, DType.INTEGER),
        ],
    )
    def test_narrowings_are_not_widenings(self, source, target):
        assert not source.widens_to(target)

    def test_widening_is_antisymmetric(self):
        """Distinct types must never widen to each other, or direction is ambiguous."""
        for left in DType:
            for right in DType:
                if left is not right and left.widens_to(right):
                    assert not right.widens_to(left)


class TestLiteralTypeMatching:
    """Value/type compatibility, exercised through allowed_values."""

    def test_boolean_values(self):
        from schemapact import Feature

        assert Feature("flag", DType.BOOLEAN, allowed_values=[True, False]).allowed_values

    def test_float_rejects_allowed_values(self):
        """Exact-float enumeration invites equality bugs, so floats reject it."""
        from schemapact import Feature
        from schemapact.exceptions import ContractDefinitionError

        with pytest.raises(ContractDefinitionError) as exc:
            Feature("ratio", DType.FLOAT, allowed_values=[0.5])
        assert exc.value.code.code == "SPX008"

    def test_boolean_rejects_integers(self):
        from schemapact import Feature
        from schemapact.exceptions import ContractDefinitionError

        with pytest.raises(ContractDefinitionError):
            Feature("flag", DType.BOOLEAN, allowed_values=[1])

    def test_date_values_are_strings(self):
        from schemapact import Feature

        assert Feature("day", DType.DATE, allowed_values=["2026-01-01"]).allowed_values
