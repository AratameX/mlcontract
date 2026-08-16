"""Inferring a starting contract from real data.

Writing the first contract by hand is the main thing standing between a new user
and any value from this library. Reading one off a file they already have turns
that into a starting point they edit.

The inference is deliberately cautious about anything that would overfit to the
sample. A contract generated from 1,000 rows describes those 1,000 rows; the
question is which of its observations are likely to hold for the next million.
Types generalise well. Observed minima and maxima do not — a range read off a
sample will reject legitimate data the moment something slightly larger arrives —
so ranges are opt-in rather than default.

This module is internal. Promoting it to the public API later is a
non-breaking change; the reverse is not.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mlcontract import _values
from mlcontract.contract import Contract, Feature
from mlcontract.dtypes import DType

MAX_CATEGORY_COUNT = 20
"""Most distinct values a column may have and still be called categorical."""

MAX_CATEGORY_RATIO = 0.5
"""Largest share of rows a column's distinct values may occupy to be categorical.

Guards against a column of mostly-unique identifiers in a short file being
mistaken for a small closed domain.
"""

# Ordered from most specific to least. The first type every value satisfies wins,
# so a column of "1", "2", "3" is integer rather than string.
_CANDIDATES = (DType.INTEGER, DType.FLOAT, DType.BOOLEAN, DType.DATE, DType.DATETIME)


def infer_from_csv(
    path: Path | str,
    *,
    name: str | None = None,
    version: str = "0.1.0",
    delimiter: str = ",",
    encoding: str = "utf-8-sig",
    infer_ranges: bool = False,
    infer_categories: bool = True,
) -> Contract:
    """Build a contract describing an existing delimited file.

    Args:
        path: The file to read.
        name: Contract name. Defaults to the file's stem.
        version: Starting version.
        delimiter: Field separator.
        encoding: Text encoding. Defaults to ``utf-8-sig``, which strips a
            byte-order mark if present and is identical to plain UTF-8 if not.
            Windows tools write UTF-8 with a BOM by default, and without this
            the mark is absorbed into the first column's name.
        infer_ranges: Whether to read ``min`` and ``max`` off the observed
            values. Off by default: a range taken from a sample rejects
            legitimate data as soon as something slightly larger appears.
        infer_categories: Whether a column with few distinct values becomes
            categorical with an ``allowed_values`` set.

    Returns:
        A contract describing the file, intended to be reviewed and edited
        rather than used as-is.

    Raises:
        ContractDefinitionError: If the file has no header row, or the inferred
            contract is somehow invalid.
    """
    location = Path(path)
    with location.open(newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        columns = list(reader.fieldnames or ())
        rows = list(reader)

    features = [
        _infer_feature(
            column,
            [row.get(column) for row in rows],
            infer_ranges=infer_ranges,
            infer_categories=infer_categories,
        )
        for column in columns
    ]

    return Contract(
        name=name or location.stem,
        version=version,
        features=features,
        description=f"Inferred from {location.name}. Review before relying on it.",
    )


def _infer_feature(
    column: str,
    raw: Sequence[str | None],
    *,
    infer_ranges: bool,
    infer_categories: bool,
) -> Feature:
    """Infer one feature from a column's raw text values."""
    present = [value for value in raw if value is not None and value != ""]
    nullable = len(present) < len(raw)

    dtype = _infer_dtype(present)
    parsed = [_values.coerce(value, dtype)[1] for value in present]

    kwargs: dict[str, Any] = {}

    if infer_categories and dtype is DType.STRING and _looks_categorical(parsed, len(raw)):
        dtype = DType.CATEGORICAL
        kwargs["allowed_values"] = sorted({str(value) for value in parsed})

    if infer_ranges and dtype in (DType.INTEGER, DType.FLOAT) and parsed:
        kwargs["min"] = min(parsed)
        kwargs["max"] = max(parsed)

    return Feature(name=column, dtype=dtype, nullable=nullable, **kwargs)


def _infer_dtype(present: Sequence[str]) -> DType:
    """Return the most specific type every value in the column parses as."""
    if not present:
        # Nothing to go on. String accepts anything, so it is the safe default
        # and the one least likely to reject real data later.
        return DType.STRING

    for candidate in _CANDIDATES:
        if all(_values.coerce(value, candidate)[0] for value in present):
            return candidate
    return DType.STRING


def _looks_categorical(values: Sequence[Any], row_count: int) -> bool:
    """Return True if a text column looks like a small closed domain."""
    distinct = {str(value) for value in values}
    if not distinct or len(distinct) > MAX_CATEGORY_COUNT:
        return False
    return len(distinct) <= max(1, int(row_count * MAX_CATEGORY_RATIO))
