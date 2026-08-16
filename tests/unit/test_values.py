"""Tests for the adapter-side value helpers."""

from __future__ import annotations

import datetime as dt

import pytest

from mlcontract import DType
from mlcontract._values import coerce, infer, is_missing


class TestIsMissing:
    def test_none(self):
        assert is_missing(None)

    def test_nan(self):
        assert is_missing(float("nan"))

    @pytest.mark.parametrize("value", [0, "", False, [], 1.5])
    def test_present_values_are_not_missing(self, value):
        """Empty string and zero are values, not absences."""
        assert not is_missing(value)


class TestInfer:
    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            ([1, 2], DType.INTEGER),
            ([1.5], DType.FLOAT),
            ([1, 2.5], DType.FLOAT),
            ([True, False], DType.BOOLEAN),
            (["a"], DType.STRING),
            ([dt.date(2026, 1, 1)], DType.DATE),
            ([dt.datetime(2026, 1, 1, 12)], DType.DATETIME),
        ],
    )
    def test_inference(self, values, expected):
        assert infer(values) is expected

    def test_nulls_are_ignored(self):
        assert infer([None, 1, None]) is DType.INTEGER

    def test_all_null_is_unknown(self):
        assert infer([None, None]) is None

    def test_empty_is_unknown(self):
        assert infer([]) is None

    @pytest.mark.parametrize("values", [[1, "a"], ["a", True], [1, "a", 2.5, True]])
    def test_genuinely_mixed_is_unknown(self, values):
        assert infer(values) is None

    def test_unrecognised_type_is_unknown(self):
        assert infer([{"nested": "object"}]) is None


class TestCoerce:
    @pytest.mark.parametrize(
        ("text", "dtype", "expected"),
        [
            ("42", DType.INTEGER, 42),
            ("-7", DType.INTEGER, -7),
            ("1.5", DType.FLOAT, 1.5),
            ("3", DType.FLOAT, 3.0),
            ("hello", DType.STRING, "hello"),
            ("IN", DType.CATEGORICAL, "IN"),
            ("2026-01-31", DType.DATE, dt.date(2026, 1, 31)),
            ("2026-01-31T12:30:00", DType.DATETIME, dt.datetime(2026, 1, 31, 12, 30)),
        ],
    )
    def test_successful_parses(self, text, dtype, expected):
        succeeded, value = coerce(text, dtype)
        assert succeeded
        assert value == expected

    @pytest.mark.parametrize(
        ("text", "dtype"),
        [
            ("abc", DType.INTEGER),
            ("1.5", DType.INTEGER),
            ("abc", DType.FLOAT),
            ("maybe", DType.BOOLEAN),
            ("31/01/2026", DType.DATE),
            ("not a time", DType.DATETIME),
        ],
    )
    def test_failed_parses_return_the_original_text(self, text, dtype):
        """The raw text is preserved so the violation can name what was there."""
        succeeded, value = coerce(text, dtype)
        assert not succeeded
        assert value == text
