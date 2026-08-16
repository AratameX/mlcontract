"""Value-level helpers shared by every adapter.

Deciding what counts as a null, and whether a Python value conforms to a
canonical type, must be answered identically no matter where the data came
from. If the CSV adapter and the pandas adapter disagreed about whether an empty
string is null, the same dataset would validate differently depending on how it
was loaded — which would make contracts useless as a shared agreement.

These answers therefore live here, once, and adapters normalise into them rather
than each deciding for itself.

Note the division of labour: this module helps adapters *produce* well-formed
values. Deciding whether a column's type satisfies a contract is the engine's
job, via :meth:`~mlcontract.dtypes.DType.accepts`. Keeping those separate means
type conformance has one implementation, not one per adapter.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from typing import Any

from mlcontract.dtypes import DType

_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_FALSE = frozenset({"false", "f", "no", "n", "0"})


def is_missing(value: Any) -> bool:
    """Return True if a value counts as null.

    Recognises ``None`` and float NaN. NaN is included because it is how pandas,
    NumPy and most numeric formats represent a missing number, and treating it
    as a present value would let missing data pass a not-null check.

    Note that empty strings are *not* null here. In a CSV an empty field is
    genuinely ambiguous — missing, or a deliberate empty string — so that
    decision belongs to the adapter that knows the format, not to this
    general-purpose helper.
    """
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def infer(values: Iterable[Any]) -> DType | None:
    """Infer the canonical type of a column from its values.

    Args:
        values: The column's values. Nulls are ignored.

    Returns:
        The inferred type, or None if the values are mixed or all null. None
        means "cannot say", and the engine then falls back to checking each
        value individually rather than reporting one misleading column-level
        type mismatch.
    """
    seen: set[DType] = set()
    for value in values:
        if is_missing(value):
            continue
        found = _classify(value)
        if found is None:
            return None
        seen.add(found)
        if len(seen) > 2:
            return None

    if not seen:
        return None
    if len(seen) == 1:
        return next(iter(seen))
    # A column of ints and floats is a float column; anything else mixed is
    # genuinely ambiguous.
    if seen == {DType.INTEGER, DType.FLOAT}:
        return DType.FLOAT
    return None


def coerce(text: str, dtype: DType) -> tuple[bool, Any]:
    """Parse a string into a canonical type, for formats that carry no types.

    CSV and similar text formats have exactly one type: string. Without
    coercion, every non-string feature in a contract would fail against every
    CSV, which would make the format useless. The contract supplies the types
    the file cannot.

    Args:
        text: The raw field.
        dtype: The type the contract declares.

    Returns:
        A ``(succeeded, value)`` pair. On failure the value is the original
        text, so the violation can report what was actually there.
    """
    try:
        if dtype is DType.INTEGER:
            return True, int(text)
        if dtype is DType.FLOAT:
            return True, float(text)
        if dtype is DType.BOOLEAN:
            lowered = text.strip().lower()
            if lowered in _TRUE:
                return True, True
            if lowered in _FALSE:
                return True, False
            return False, text
        if dtype is DType.DATE:
            return True, dt.date.fromisoformat(text)
        if dtype is DType.DATETIME:
            return True, dt.datetime.fromisoformat(text)
    except ValueError:
        return False, text
    return True, text


def _classify(value: Any) -> DType | None:
    """Return the canonical type of a single Python value, or None if unknown."""
    if isinstance(value, bool):
        return DType.BOOLEAN
    if isinstance(value, int):
        return DType.INTEGER
    if isinstance(value, float):
        return DType.FLOAT
    if isinstance(value, str):
        return DType.STRING
    if isinstance(value, dt.datetime):
        return DType.DATETIME
    if isinstance(value, dt.date):
        return DType.DATE
    return None
