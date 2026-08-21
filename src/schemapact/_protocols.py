"""The boundary between the validation engine and whatever holds the data.

The engine validates ``list[dict]``, CSV files, pandas DataFrames and, later,
Polars and Arrow tables. It manages that without importing any of them: it talks
only to :class:`DataSource`, and each adapter implements that protocol for its
own backend.

This is the single most consequential decision in the library. If the engine
ever reaches for a pandas method directly, every future backend becomes a
rewrite rather than a new file. The rule is absolute: nothing in
:mod:`schemapact._engine` may know what kind of data it is looking at.

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

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from schemapact.dtypes import DType


@dataclass(frozen=True, slots=True)
class Failures:
    """What a single value check found, without materialising every offender.

    Separating the count from the samples is deliberate. A report needs the
    exact number of affected rows and only a handful of examples, so keeping
    every offending pair to show five of them wastes memory in proportion to how
    broken the data is — worst exactly when the dataset is largest.

    Attributes:
        count: How many rows failed, in full.
        samples: Up to the caller's limit of ``(row, value)`` pairs.
        extreme: The furthest offending value, for bounds checks. None when the
            check has no natural extreme.
        distinct: Distinct offending values, for domain and uniqueness checks,
            capped by the producer.
    """

    count: int
    samples: tuple[tuple[int, Any], ...] = ()
    extreme: Any = None
    distinct: tuple[Any, ...] = ()

    @property
    def any(self) -> bool:
        """Return True if anything failed."""
        return self.count > 0


@runtime_checkable
class VectorisedSource(Protocol):
    """An optional fast path for backends that evaluate whole columns at once.

    The engine's default is to iterate a column in Python, which is correct for
    every backend and slow for the ones that could do better. A source
    implementing any of these methods gets that check evaluated in one
    vectorised operation instead.

    Every method may return ``None``, meaning "no fast path for this" — the
    engine then falls back to iteration. That makes the protocol genuinely
    optional per check: an adapter can accelerate what it can express and ignore
    the rest, rather than facing an all-or-nothing implementation.

    The results must be *identical* to what iteration would produce, not merely
    similar. Tests assert that the two paths agree on the same data, because a
    fast path that quietly disagrees with the slow one is worse than no fast
    path at all.
    """

    def failing_below(self, column: str, minimum: float, *, limit: int) -> Failures | None:
        """Rows whose value is below an inclusive minimum."""
        ...

    def failing_above(self, column: str, maximum: float, *, limit: int) -> Failures | None:
        """Rows whose value is above an inclusive maximum."""
        ...

    def failing_outside(
        self, column: str, allowed: Collection[Any], *, limit: int
    ) -> Failures | None:
        """Rows whose value is not in the permitted domain."""
        ...

    def failing_pattern(self, column: str, pattern: str, *, limit: int) -> Failures | None:
        """Rows whose value does not fully match a regular expression."""
        ...

    def failing_duplicates(self, column: str, *, limit: int) -> Failures | None:
        """Rows holding a value that appears more than once."""
        ...


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
