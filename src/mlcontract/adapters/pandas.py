"""Adapter for pandas DataFrames.

Imported lazily and only on demand, so the core stays free of pandas. Nothing
here is referenced by :mod:`mlcontract._engine`; the engine sees only the
data-source protocol.

The interesting work is type mapping. pandas has many ways to spell the same
canonical type — ``int64``, ``Int64``, ``int32`` are all integers — and several
that mean "no useful information", chiefly ``object``. Getting this wrong makes
a contract either reject valid data or accept invalid data, so the mapping is
explicit and tested per dtype rather than inferred from names.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from re import error as re_error
from typing import TYPE_CHECKING, Any

from mlcontract import _values
from mlcontract._protocols import Failures
from mlcontract.dtypes import DType
from mlcontract.exceptions import missing_dependency

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def require_pandas() -> Any:
    """Import pandas, or raise an error naming the extra to install."""
    try:
        import pandas
    except ImportError as exc:  # pragma: no cover - depends on install shape
        raise missing_dependency(
            package="pandas",
            extra="pandas",
            purpose="Validating pandas DataFrames",
        ) from exc
    return pandas


def _require_numpy() -> Any:
    """Import NumPy, which pandas already depends on."""
    import numpy

    return numpy


class PandasSource:
    """A data source over a :class:`pandas.DataFrame`.

    Args:
        frame: The DataFrame to validate.
        description: How this data should be named in reports. Defaults to a
            description of its shape.
    """

    def __init__(self, frame: pd.DataFrame, *, description: str | None = None) -> None:
        self._pd = require_pandas()
        self._np = _require_numpy()
        self._frame = frame
        rows, columns = frame.shape
        self._description = description or f"DataFrame ({rows} rows x {columns} columns)"

    def describe(self) -> str:
        """Return the name used for this data in reports."""
        return self._description

    def column_names(self) -> tuple[str, ...]:
        """Return the column labels, in frame order."""
        return tuple(str(name) for name in self._frame.columns)

    def row_count(self) -> int:
        """Return the number of rows."""
        return len(self._frame.index)

    def observed_dtype(self, column: str) -> DType | None:
        """Map the column's pandas dtype onto a canonical type.

        Returns None when pandas cannot say — an ``object`` column of mixed
        values, or a column that is entirely null. The engine treats None as
        "mixed" and reports it, which is more honest than guessing.
        """
        series = self._frame[column]
        dtype = series.dtype

        if isinstance(dtype, self._pd.CategoricalDtype):
            return DType.CATEGORICAL

        # Nullable extension dtypes (Int64, Float64, boolean) share these kind
        # codes with their NumPy counterparts, so one check covers both.
        kind = getattr(dtype, "kind", "")
        if kind in "iu":
            return DType.INTEGER
        if kind == "f":
            return self._float_or_promoted_integer(series)
        if kind == "b":
            return DType.BOOLEAN
        if kind == "M":
            # Covers tz-naive and tz-aware alike. A contract declares "datetime";
            # whether a timezone is attached is a separate concern this release
            # does not attempt to express.
            return DType.DATETIME

        if isinstance(dtype, self._pd.StringDtype):
            return DType.STRING

        # Anything left is `object` or an extension type we do not recognise.
        # Inspect the values rather than assume: an object column may hold
        # strings, dates, or a genuine mixture.
        return _values.infer(self._values_of(column))

    def _float_or_promoted_integer(self, series: Any) -> DType | None:
        """Distinguish real floats from integers pandas promoted to float.

        A NumPy integer column cannot hold a null, so pandas silently converts
        it to ``float64`` the moment one appears. ``[30, 12, None]`` is stored as
        float and is semantically still integers — and a contract declaring
        ``integer`` would fail against it for a reason that has nothing to do
        with the data.

        Treating that case as integer is a deliberate accommodation, kept as
        narrow as possible: only a float column that *contains nulls* and whose
        every present value is a whole number qualifies. A float column without
        nulls is taken at face value, so genuine float data is never quietly
        accepted where an integer was required. Users who want the distinction
        enforced strictly can store the column as pandas' nullable ``Int64``,
        which carries the intent explicitly.

        Both checks are vectorised, so this costs a pass in C rather than a
        Python loop.
        """
        if not bool(series.isna().any()):
            return DType.FLOAT

        present = series.dropna()
        if len(present) == 0:
            # Entirely null: nothing to go on, and saying "float" would be an
            # assertion the data does not support.
            return None

        return DType.INTEGER if bool((present % 1 == 0).all()) else DType.FLOAT

    def null_count(self, column: str) -> int:
        """Count missing values using pandas' own definition.

        Delegating to ``isna`` matters: pandas has four spellings of missing —
        ``NaN``, ``None``, ``NaT`` and ``pd.NA`` — and each appears in different
        dtypes. Reimplementing that here would eventually disagree with pandas.
        """
        return int(self._frame[column].isna().sum())

    def iter_values(self, column: str) -> Iterator[tuple[int, Any]]:
        """Yield ``(row_position, value)`` for every non-null value.

        Row positions are positional, not index labels, so they stay meaningful
        for frames with a non-integer or non-unique index.

        Values are converted to plain Python types. This is not incidental:
        ``numpy.int64`` is not a Python ``int``, so leaving values as NumPy
        scalars would make every ``isinstance`` check in the engine fail and
        every integer column look mixed.

        Note the order: rows are numbered *before* nulls are filtered out.
        Enumerating the surviving values instead would shift every row number
        after the first null, so a report would point at the wrong rows in
        exactly the datasets most likely to have problems.
        """
        series = self._frame[column]
        isna = self._pd.isna
        for position, value in enumerate(series.tolist()):
            if not _is_scalar_na(isna, value):
                yield position, value

    # ------------------------------------------------------------------
    def _values_of(self, column: str) -> Iterator[Any]:
        """Yield the column's non-null values, without row numbers.

        Used for type inference, where positions are irrelevant.
        """
        series = self._frame[column]
        isna = self._pd.isna
        for value in series.tolist():
            if not _is_scalar_na(isna, value):
                yield value

    # ----------------------------------------------------------------------
    # Vectorised fast paths
    #
    # These implement mlcontract._protocols.VectorisedSource. Each evaluates a
    # whole column in one pandas operation instead of a Python loop, and each
    # returns None when it cannot express the check — the engine then falls back
    # to iteration, so correctness never depends on a fast path existing.
    #
    # Two invariants every one of these must hold, both covered by tests that
    # run the same data through both paths and compare the reports:
    #
    #   * nulls are never reported. A missing value is the nullability check's
    #     business, and a comparison against NaN is False anyway, so nulls drop
    #     out naturally — but `notna()` is applied explicitly rather than relied
    #     upon, because that is not true of every dtype.
    #   * row numbers are positional, so they stay meaningful for a frame with a
    #     non-default or non-unique index.
    # ----------------------------------------------------------------------

    def failing_below(self, column: str, minimum: float, *, limit: int) -> Failures | None:
        """Rows below an inclusive minimum, evaluated in one pass."""
        return self._compare(column, minimum, below=True, limit=limit)

    def failing_above(self, column: str, maximum: float, *, limit: int) -> Failures | None:
        """Rows above an inclusive maximum, evaluated in one pass."""
        return self._compare(column, maximum, below=False, limit=limit)

    def failing_outside(
        self, column: str, allowed: Collection[Any], *, limit: int
    ) -> Failures | None:
        """Rows whose value is not in the permitted domain."""
        series = self._frame[column]
        mask = ~series.isin(list(allowed)) & series.notna()
        return self._collect(series, mask, limit=limit, distinct=True)

    def failing_pattern(self, column: str, pattern: str, *, limit: int) -> Failures | None:
        """Rows not fully matching a regular expression."""
        series = self._frame[column]
        if not (isinstance(series.dtype, self._pd.StringDtype) or series.dtype == object):
            # A non-text column fails the pattern check for every present value,
            # but saying so precisely is the slow path's job — it can report the
            # actual offending values rather than a blanket count.
            return None

        try:
            matched = series.str.fullmatch(pattern, na=False)
        except (TypeError, ValueError, re_error):  # pragma: no cover
            # Mixed object columns, or a pattern pandas' regex engine rejects
            # where Python's does not. Which inputs reach here varies by pandas
            # version, so this is defensive rather than a path any current
            # release exercises. Declining always falls back to iteration, so
            # correctness does not depend on it.
            return None

        mask = ~matched.astype(bool) & series.notna()
        return self._collect(series, mask, limit=limit)

    def failing_duplicates(self, column: str, *, limit: int) -> Failures | None:
        """Rows holding a value that appears more than once."""
        series = self._frame[column]
        mask = series.duplicated(keep=False) & series.notna()
        return self._collect(series, mask, limit=limit, distinct=True)

    # -- shared machinery ---------------------------------------------------

    def _compare(self, column: str, bound: float, *, below: bool, limit: int) -> Failures | None:
        """Evaluate a numeric bound, or decline if the column is not numeric."""
        series = self._frame[column]
        if getattr(series.dtype, "kind", "") not in "iuf":
            # A non-numeric column has already failed its type check, or holds
            # mixed values the slow path describes better.
            return None

        mask = (series < bound) if below else (series > bound)
        return self._collect(
            series, mask.fillna(False), limit=limit, extreme="min" if below else "max"
        )

    def _collect(
        self,
        series: Any,
        mask: Any,
        *,
        limit: int,
        extreme: str | None = None,
        distinct: bool = False,
    ) -> Failures:
        """Turn a boolean mask into a Failures record.

        Only the sampled rows are converted to Python objects. Converting the
        whole failing set would undo the point of evaluating in NumPy, and on a
        badly broken column that set can be the entire frame.
        """
        positions = self._np.flatnonzero(mask.to_numpy(dtype=bool, na_value=False))
        count = int(positions.size)
        if count == 0:
            return Failures(count=0)

        sampled = positions[:limit]
        samples = tuple(
            (int(position), _python(series.iloc[int(position)])) for position in sampled
        )

        worst: Any = None
        if extreme is not None:
            failing = series[mask]
            worst = _python(failing.min() if extreme == "min" else failing.max())

        found: tuple[Any, ...] = ()
        if distinct:
            try:
                unique = series[mask].dropna().unique()
            except TypeError:
                # An object column may hold unhashable values such as lists.
                # The count and samples above are still correct; only the
                # distinct-value summary is unavailable, and omitting it is far
                # better than failing the whole validation run over a detail
                # used to make one message friendlier.
                unique = []
            found = tuple(_python(value) for value in unique[:_DISTINCT_LIMIT])

        return Failures(count=count, samples=samples, extreme=worst, distinct=found)


def _is_scalar_na(isna: Any, value: Any) -> bool:
    """Return True if pandas considers a scalar missing.

    Guarded because ``pandas.isna`` returns an array for list-like input, and an
    ``object`` column may legitimately contain lists. Falling back to the
    stdlib check keeps such a value as present rather than raising.
    """
    try:
        return bool(isna(value))
    except (TypeError, ValueError):  # pragma: no cover - list-like cell contents
        return _values.is_missing(value)


_DISTINCT_LIMIT = 50
"""How many distinct offending values to retain for a violation message."""


def _python(value: Any) -> Any:
    """Convert a NumPy or pandas scalar to a plain Python object.

    Reports are serialised to JSON and compared against values from other
    adapters, and ``numpy.int64`` is neither JSON-serialisable nor equal in type
    to the ``int`` the stdlib adapter would have produced.
    """
    item = getattr(value, "item", None)
    return item() if callable(item) else value
