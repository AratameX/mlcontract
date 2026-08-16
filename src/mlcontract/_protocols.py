"""The boundary between the validation engine and whatever holds the data.

The engine validates ``list[dict]``, CSV files, pandas DataFrames and, later,
Polars and Arrow tables. It manages that without importing any of them: it talks
only to :class:`DataSource`, and each adapter implements that protocol for its
own backend.

This is the single most consequential decision in the library. If the engine
ever reaches for a pandas method directly, every future backend becomes a
rewrite rather than a new file. The rule is absolute: nothing in
:mod:`mlcontract._engine` may know what kind of data it is looking at.

The protocol is deliberately small — six methods, all straightforward to
implement over any tabular structure. Adding one is a cost paid by every adapter
that will ever exist, so the bar is high.

Note on vectorisation: this protocol iterates values row by row, which is the
right baseline because every backend can do it. Backends that can evaluate a
predicate over a whole column at once will get optional fast-path methods in the
pandas phase — designed against a real implementation rather than guessed at
now, since a fast-path interface invented without one tends not to fit.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol, runtime_checkable

from mlcontract.dtypes import DType


@runtime_checkable
class DataSource(Protocol):
    """A read-only, column-addressable view of tabular data.

    Implementations must be side-effect free: validation never modifies the data
    it inspects, and calling any method twice must give the same answer.
    """

    def describe(self) -> str:
        """Return a short human-readable name for this data, used in reports.

        For example ``"list of 500 mappings"`` or ``"customers.csv"``. Appears in
        report output so a failure can be traced back to its source.
        """
        ...

    def column_names(self) -> tuple[str, ...]:
        """Return the columns present, in their natural order.

        Order matters: it is what ``enforce_column_order`` checks against.
        """
        ...

    def row_count(self) -> int:
        """Return the number of rows."""
        ...

    def observed_dtype(self, column: str) -> DType | None:
        """Return the canonical type of a column's values.

        Args:
            column: The column to inspect. Guaranteed by the engine to exist.

        Returns:
            The canonical type, or None if the column holds a mix of types that
            no single canonical type describes. None is a meaningful answer, not
            a failure — mixed columns are a real and reportable condition.
        """
        ...

    def null_count(self, column: str) -> int:
        """Return how many values in a column are null.

        What counts as null is the adapter's decision, because it differs by
        backend: ``None`` for mappings, empty fields for CSV, ``NaN`` and ``NaT``
        for pandas.
        """
        ...

    def iter_values(self, column: str) -> Iterator[tuple[int, Any]]:
        """Yield ``(row_index, value)`` for every non-null value in a column.

        Nulls are excluded because every value-level constraint applies only to
        values that exist; nullability is checked separately. Row indices are
        zero-based and refer to position in the data, so they stay meaningful
        for sources that have no index of their own.
        """
        ...


def column_values(source: DataSource, column: str) -> Sequence[Any]:
    """Collect a column's non-null values, discarding row positions.

    A convenience for checks that care about the multiset of values rather than
    where each one sits, such as uniqueness.
    """
    return [value for _, value in source.iter_values(column)]
