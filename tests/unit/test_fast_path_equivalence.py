"""The vectorised path must agree with iteration, exactly.

A fast path that quietly disagrees with the slow one is worse than no fast path
at all: it produces confident, wrong reports on exactly the large datasets where
nobody will check by hand.

Every test here runs the same data through the same adapter twice — once with
the vectorised methods available and once with them hidden — and compares the
entire report, not a summary of it.

This is not hypothetical diligence. Writing these comparisons is what exposed a
row-numbering bug in the *iterating* path, where positions closed up behind
nulls and every reported row after the first null pointed at the wrong record.
"""

from __future__ import annotations

from typing import Any

import pytest

from mlcontract import Contract, DType, Feature
from tests._support import requires_pandas

pd = pytest.importorskip("pandas", reason="requires the 'pandas' extra")

pytestmark = requires_pandas


class SlowOnly:
    """Wraps a source, exposing only the mandatory protocol.

    Hiding the vectorised methods forces the engine down its fallback path, so
    the two can be compared on identical data.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def describe(self) -> str:
        return str(self._inner.describe())

    def column_names(self) -> Any:
        return self._inner.column_names()

    def row_count(self) -> int:
        return int(self._inner.row_count())

    def observed_dtype(self, column: str) -> Any:
        return self._inner.observed_dtype(column)

    def null_count(self, column: str) -> int:
        return int(self._inner.null_count(column))

    def iter_values(self, column: str) -> Any:
        return self._inner.iter_values(column)


def both_paths(contract: Contract, frame: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate through the vectorised and iterating paths, and return both reports."""
    from mlcontract.adapters.pandas import PandasSource

    source = PandasSource(frame)
    fast = contract.validate(source).to_dict()
    slow = contract.validate(SlowOnly(source)).to_dict()
    # Only the description differs by construction.
    fast["source"] = slow["source"] = "-"
    return fast, slow


def assert_identical(contract: Contract, frame: Any) -> None:
    fast, slow = both_paths(contract, frame)
    assert fast == slow


def one(feature: Feature) -> Contract:
    return Contract(name="t", version="1.0.0", features=[feature])


class TestRanges:
    def test_below_minimum(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, min=10)),
            pd.DataFrame({"a": [5, 50, 2, 99]}),
        )

    def test_above_maximum(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, max=10)),
            pd.DataFrame({"a": [5, 50, 2, 99]}),
        )

    def test_both_bounds(self):
        assert_identical(
            one(Feature("a", DType.FLOAT, min=0.0, max=1.0)),
            pd.DataFrame({"a": [-1.5, 0.5, 2.0, 0.0, 1.0]}),
        )

    def test_with_nulls(self):
        """The case that exposed the row-numbering bug."""
        assert_identical(
            one(Feature("a", DType.FLOAT, min=0.0)),
            pd.DataFrame({"a": [-1.0, None, -2.0, None, 3.0]}),
        )

    def test_all_values_failing(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, min=100)),
            pd.DataFrame({"a": [1, 2, 3]}),
        )

    def test_no_values_failing(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, min=0)),
            pd.DataFrame({"a": [1, 2, 3]}),
        )

    def test_boundary_values_are_inclusive(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, min=5, max=10)),
            pd.DataFrame({"a": [5, 10]}),
        )

    def test_nullable_integer_dtype(self):
        assert_identical(
            one(Feature("a", DType.INTEGER, min=3)),
            pd.DataFrame({"a": pd.array([1, None, 5], dtype="Int64")}),
        )


class TestAllowedValues:
    def test_unexpected_categories(self):
        assert_identical(
            one(Feature("c", DType.CATEGORICAL, allowed_values=["a", "b"])),
            pd.DataFrame({"c": ["a", "z", "b", "q", "z"]}),
        )

    def test_with_nulls(self):
        assert_identical(
            one(Feature("c", DType.CATEGORICAL, allowed_values=["a"])),
            pd.DataFrame({"c": ["a", None, "z", None]}),
        )

    def test_integer_domain(self):
        assert_identical(
            one(Feature("c", DType.INTEGER, allowed_values=[1, 2])),
            pd.DataFrame({"c": [1, 2, 3, 1]}),
        )

    def test_categorical_dtype(self):
        assert_identical(
            one(Feature("c", DType.CATEGORICAL, allowed_values=["a", "b"])),
            pd.DataFrame({"c": pd.Categorical(["a", "z", "b"])}),
        )


class TestPatterns:
    def test_mismatches(self):
        assert_identical(
            one(Feature("e", DType.STRING, pattern=r"^[a-z]+$")),
            pd.DataFrame({"e": ["abc", "AB1", "xyz", "9"]}),
        )

    def test_with_nulls(self):
        assert_identical(
            one(Feature("e", DType.STRING, pattern=r"^\d+$")),
            pd.DataFrame({"e": ["1", None, "x", None, "22"]}),
        )

    def test_full_match_not_substring(self):
        """A pattern must describe the whole value in both paths."""
        assert_identical(
            one(Feature("e", DType.STRING, pattern=r"\d+")),
            pd.DataFrame({"e": ["123", "a123", "123a"]}),
        )

    def test_every_value_matching(self):
        assert_identical(
            one(Feature("e", DType.STRING, pattern=r"^[a-z]+$")),
            pd.DataFrame({"e": ["abc", "def"]}),
        )


class TestUniqueness:
    def test_duplicates(self):
        assert_identical(
            one(Feature("u", DType.INTEGER, unique=True)),
            pd.DataFrame({"u": [1, 2, 1, 3, 2]}),
        )

    def test_nulls_are_not_duplicates(self):
        """Two missing values are not the same value repeated."""
        assert_identical(
            one(Feature("u", DType.INTEGER, unique=True)),
            pd.DataFrame({"u": [1.0, None, None, 2.0]}),
        )

    def test_all_distinct(self):
        assert_identical(
            one(Feature("u", DType.INTEGER, unique=True)),
            pd.DataFrame({"u": [1, 2, 3]}),
        )

    def test_string_duplicates(self):
        assert_identical(
            one(Feature("u", DType.STRING, unique=True)),
            pd.DataFrame({"u": ["a", "b", "a"]}),
        )


class TestDeclines:
    @staticmethod
    def source(frame: Any) -> Any:
        from mlcontract.adapters.pandas import PandasSource

        return PandasSource(frame)

    def test_a_bound_on_a_text_column_declines(self):
        frame = pd.DataFrame({"a": ["x", "y"]})
        assert self.source(frame).failing_below("a", 0, limit=5) is None

    def test_a_bound_on_a_mixed_object_column_declines(self):
        frame = pd.DataFrame({"a": pd.Series([1.0, "oops"], dtype=object)})
        assert self.source(frame).failing_above("a", 0, limit=5) is None

    def test_a_pattern_on_a_numeric_column_declines(self):
        frame = pd.DataFrame({"a": pd.Series([1, 2], dtype="int64")})
        assert self.source(frame).failing_pattern("a", r"[a-z]+", limit=5) is None

    def test_unhashable_values_omit_only_the_distinct_summary(self):
        frame = pd.DataFrame({"a": pd.Series([["x"], ["x"]], dtype=object)})
        result = self.source(frame).failing_duplicates("a", limit=5)
        assert result is None or result.distinct == ()


class TestCombined:
    def test_every_check_at_once(self):
        contract = Contract(
            name="t",
            version="1.0.0",
            features=[
                Feature("n", DType.INTEGER, min=10, max=90),
                Feature("c", DType.CATEGORICAL, allowed_values=["a", "b"]),
                Feature("e", DType.STRING, pattern=r"^[a-z]+$"),
                Feature("u", DType.INTEGER, unique=True),
                Feature("f", DType.FLOAT, min=0.0),
            ],
        )
        frame = pd.DataFrame(
            [
                {"n": 5, "c": "a", "e": "abc", "u": 1, "f": -1.5},
                {"n": 50, "c": "z", "e": "AB1", "u": 1, "f": 2.0},
                {"n": 99, "c": "b", "e": "xyz", "u": 2, "f": 0.0},
                {"n": None, "c": None, "e": None, "u": None, "f": None},
                {"n": 2, "c": "q", "e": "9", "u": 3, "f": -0.1},
            ]
        )
        assert_identical(contract, frame)

    def test_an_empty_frame(self):
        contract = one(Feature("a", DType.INTEGER, min=0, unique=True))
        assert_identical(contract, pd.DataFrame({"a": pd.Series(dtype="int64")}))

    def test_a_non_default_index(self):
        """Row numbers are positional, so both paths must ignore index labels."""
        frame = pd.DataFrame({"a": [5, 50, 2]}, index=["x", "y", "z"])
        assert_identical(one(Feature("a", DType.INTEGER, min=10)), frame)

    def test_samples_are_capped_identically(self):
        contract = one(Feature("a", DType.INTEGER, min=0))
        frame = pd.DataFrame({"a": list(range(-50, 0))})
        from mlcontract.adapters.pandas import PandasSource

        source = PandasSource(frame)
        fast = contract.validate(source, max_samples=3).to_dict()
        slow = contract.validate(SlowOnly(source), max_samples=3).to_dict()
        fast["source"] = slow["source"] = "-"
        assert fast == slow
        assert len(fast["violations"][0]["samples"]) == 3

    def test_suppressed_samples_agree(self):
        contract = one(Feature("a", DType.INTEGER, min=0))
        frame = pd.DataFrame({"a": [-1, -2, 3]})
        from mlcontract.adapters.pandas import PandasSource

        source = PandasSource(frame)
        fast = contract.validate(source, sample_values=False).to_dict()
        slow = contract.validate(SlowOnly(source), sample_values=False).to_dict()
        fast["source"] = slow["source"] = "-"
        assert fast == slow
