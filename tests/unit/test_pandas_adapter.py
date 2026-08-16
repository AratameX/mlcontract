"""Tests for the pandas adapter.

pandas offers several spellings of every canonical type and four spellings of
"missing", so the mapping is tested dtype by dtype rather than by sampling a
couple of happy cases.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from mlcontract import Contract, DType, Feature
from tests._support import requires_pandas

pd = pytest.importorskip("pandas", reason="requires the 'pandas' extra")

pytestmark = requires_pandas


def source(frame: Any) -> Any:
    from mlcontract.adapters.pandas import PandasSource

    return PandasSource(frame)


def contract(*features: Feature, **overrides: Any) -> Contract:
    defaults: dict[str, Any] = {"name": "t", "version": "1.0.0", "features": features}
    return Contract(**{**defaults, **overrides})


class TestShape:
    def test_column_names_in_frame_order(self):
        assert source(pd.DataFrame({"b": [1], "a": [2]})).column_names() == ("b", "a")

    def test_row_count(self):
        assert source(pd.DataFrame({"a": [1, 2, 3]})).row_count() == 3

    def test_empty_frame(self):
        frame = pd.DataFrame({"a": pd.Series(dtype="int64")})
        assert source(frame).row_count() == 0

    def test_description_reports_the_shape(self):
        assert "2 rows x 1 columns" in source(pd.DataFrame({"a": [1, 2]})).describe()


class TestDtypeMapping:
    @pytest.mark.parametrize(
        ("values", "dtype", "expected"),
        [
            ([1, 2], "int64", DType.INTEGER),
            ([1, 2], "int32", DType.INTEGER),
            ([1, 2], "int8", DType.INTEGER),
            ([1, 2], "uint8", DType.INTEGER),
            ([1, 2], "Int64", DType.INTEGER),
            ([1.5, 2.5], "float64", DType.FLOAT),
            ([1.5, 2.5], "float32", DType.FLOAT),
            ([1.5, 2.5], "Float64", DType.FLOAT),
            ([True, False], "bool", DType.BOOLEAN),
            ([True, False], "boolean", DType.BOOLEAN),
            (["a", "b"], "str", DType.STRING),
        ],
    )
    def test_scalar_dtypes(self, values, dtype, expected):
        frame = pd.DataFrame({"a": pd.array(values, dtype=dtype)})
        assert source(frame).observed_dtype("a") is expected

    def test_categorical(self):
        frame = pd.DataFrame({"a": pd.Categorical(["x", "y"])})
        assert source(frame).observed_dtype("a") is DType.CATEGORICAL

    def test_datetime(self):
        frame = pd.DataFrame({"a": pd.to_datetime(["2026-01-01"])})
        assert source(frame).observed_dtype("a") is DType.DATETIME

    def test_timezone_aware_datetime(self):
        """Timezone awareness is a separate concern this release does not express."""
        frame = pd.DataFrame({"a": pd.to_datetime(["2026-01-01"]).tz_localize("UTC")})
        assert source(frame).observed_dtype("a") is DType.DATETIME

    def test_dates_in_an_object_column(self):
        frame = pd.DataFrame({"a": [dt.date(2026, 1, 1)]})
        assert source(frame).observed_dtype("a") is DType.DATE

    def test_mixed_object_column_is_unknown(self):
        frame = pd.DataFrame({"a": pd.Series([1, "x"], dtype=object)})
        assert source(frame).observed_dtype("a") is None

    def test_all_null_column_is_unknown(self):
        frame = pd.DataFrame({"a": [None, None]})
        assert source(frame).observed_dtype("a") is None


class TestIntegerPromotion:
    """pandas turns an integer column into float64 as soon as a null appears.

    That is a storage artifact, not a change in the data, and treating it as a
    type violation would fail contracts for a reason unrelated to their data.
    """

    def test_promoted_integers_are_still_integers(self):
        frame = pd.DataFrame({"a": [30, 12, None]})
        assert str(frame["a"].dtype) == "float64"
        assert source(frame).observed_dtype("a") is DType.INTEGER

    def test_genuine_floats_with_nulls_stay_float(self):
        frame = pd.DataFrame({"a": [1.5, None]})
        assert source(frame).observed_dtype("a") is DType.FLOAT

    def test_whole_floats_without_nulls_stay_float(self):
        """Without a null there was no promotion, so the dtype is taken at face value."""
        frame = pd.DataFrame({"a": [1.0, 2.0]})
        assert source(frame).observed_dtype("a") is DType.FLOAT

    def test_infinity_is_not_a_whole_number(self):
        frame = pd.DataFrame({"a": [float("inf"), None]})
        assert source(frame).observed_dtype("a") is DType.FLOAT

    def test_all_null_float_column_is_unknown(self):
        """Nothing present to judge by, so claiming a type would overstate it."""
        frame = pd.DataFrame({"a": pd.Series([None, None], dtype="float64")})
        assert source(frame).observed_dtype("a") is None

    def test_nullable_int64_needs_no_accommodation(self):
        frame = pd.DataFrame({"a": pd.array([1, None], dtype="Int64")})
        assert source(frame).observed_dtype("a") is DType.INTEGER

    def test_end_to_end(self):
        report = contract(Feature("age", DType.INTEGER)).validate(
            pd.DataFrame({"age": [30, 12, None]})
        )
        assert report.is_valid


class TestNulls:
    @pytest.mark.parametrize(
        "frame_data",
        [
            {"a": [1.0, float("nan")]},
            {"a": pd.array([1, None], dtype="Int64")},
            {"a": pd.to_datetime(["2026-01-01", None])},
            {"a": pd.Series([1, None], dtype=object)},
        ],
    )
    def test_every_pandas_spelling_of_missing(self, frame_data):
        """NaN, pd.NA, NaT and None each appear in different dtypes."""
        assert source(pd.DataFrame(frame_data)).null_count("a") == 1

    def test_no_nulls(self):
        assert source(pd.DataFrame({"a": [1, 2]})).null_count("a") == 0


class TestValues:
    def test_values_are_python_types_not_numpy_scalars(self):
        """numpy.int64 is not a Python int, so unconverted scalars break the engine."""
        _, value = next(iter(source(pd.DataFrame({"a": [1]})).iter_values("a")))
        assert type(value) is int

    def test_nulls_are_skipped_and_positions_preserved(self):
        frame = pd.DataFrame({"a": [1.0, None, 3.0]})
        assert list(source(frame).iter_values("a")) == [(0, 1.0), (1, 3.0)]

    def test_positions_are_positional_not_index_labels(self):
        """A frame with a non-default index must still report row positions."""
        frame = pd.DataFrame({"a": [10, 20]}, index=["x", "y"])
        assert [row for row, _ in source(frame).iter_values("a")] == [0, 1]

    def test_timestamps_satisfy_a_datetime_contract(self):
        report = contract(Feature("t", DType.DATETIME)).validate(
            pd.DataFrame({"t": pd.to_datetime(["2026-01-01"])})
        )
        assert report.is_valid


class TestEndToEnd:
    def test_clean_frame_passes(self):
        report = contract(
            Feature("age", DType.INTEGER, nullable=False, min=18),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"]),
        ).validate(pd.DataFrame({"age": [30, 41], "country": ["IN", "US"]}))
        assert report.is_valid

    def test_violations_are_found(self):
        report = contract(
            Feature("age", DType.INTEGER, nullable=False, min=18),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"]),
        ).validate(pd.DataFrame({"age": [12, 41], "country": ["FR", "US"]}))
        assert {v.code.code for v in report.violations} == {"MLC203", "MLC205"}

    def test_uniqueness(self):
        report = contract(Feature("id", DType.INTEGER, unique=True)).validate(
            pd.DataFrame({"id": [1, 2, 1]})
        )
        assert [v.code.code for v in report.violations] == ["MLC207"]

    def test_pattern(self):
        report = contract(Feature("e", DType.STRING, pattern=r"^[^@]+@[^@]+$")).validate(
            pd.DataFrame({"e": ["a@b.com", "nope"]})
        )
        assert [v.code.code for v in report.violations] == ["MLC206"]

    def test_row_bounds(self):
        report = contract(Feature("a", DType.INTEGER), min_rows=5).validate(
            pd.DataFrame({"a": [1]})
        )
        assert [v.code.code for v in report.violations] == ["MLC105"]

    def test_extra_column_warns(self):
        report = contract(Feature("a", DType.INTEGER)).validate(pd.DataFrame({"a": [1], "b": [2]}))
        assert report.is_valid
        assert [v.code.code for v in report.violations] == ["MLC102"]

    def test_report_names_the_source(self):
        report = contract(Feature("a", DType.INTEGER)).validate(pd.DataFrame({"a": [1]}))
        assert "DataFrame" in report.source

    def test_resolve_picks_the_pandas_adapter(self):
        from mlcontract.adapters import resolve
        from mlcontract.adapters.pandas import PandasSource

        chosen = resolve(pd.DataFrame({"a": [1]}), contract(Feature("a", DType.INTEGER)))
        assert isinstance(chosen, PandasSource)
