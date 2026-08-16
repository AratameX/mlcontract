"""Adapters for data structures available in the standard library.

Neither of these needs a third-party package, which is what makes
``pip install mlcontract`` immediately useful and keeps the engine honest: if a
pandas assumption ever leaked into the core, these adapters would break and CI
would catch it.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mlcontract import _values
from mlcontract.dtypes import DType

if TYPE_CHECKING:
    from mlcontract.contract import Contract


class MappingSource:
    """A data source over a sequence of mappings, such as ``list[dict]``.

    Columns are the union of every row's keys, ordered by first appearance. A
    key absent from a row is treated as null for that row, which is what makes
    JSON-shaped records with optional fields work naturally.

    Args:
        rows: The records to validate.
        description: How this data should be named in reports.
    """

    def __init__(
        self, rows: Sequence[Mapping[str, Any]], *, description: str | None = None
    ) -> None:
        self._rows = rows
        self._description = description or f"list of {len(rows)} mappings"
        self._columns: tuple[str, ...] | None = None

    def describe(self) -> str:
        """Return the name used for this data in reports."""
        return self._description

    def column_names(self) -> tuple[str, ...]:
        """Return every key seen across the rows, in order of first appearance."""
        if self._columns is None:
            seen: dict[str, None] = {}
            for row in self._rows:
                for key in row:
                    seen.setdefault(key, None)
            self._columns = tuple(seen)
        return self._columns

    def row_count(self) -> int:
        """Return the number of records."""
        return len(self._rows)

    def observed_dtype(self, column: str) -> DType | None:
        """Infer the column's type, or None if its values are mixed."""
        return _values.infer(row.get(column) for row in self._rows)

    def null_count(self, column: str) -> int:
        """Count missing values, treating an absent key as null."""
        return sum(1 for row in self._rows if _values.is_missing(row.get(column)))

    def iter_values(self, column: str) -> Iterator[tuple[int, Any]]:
        """Yield ``(row_index, value)`` for every non-null value."""
        for index, row in enumerate(self._rows):
            value = row.get(column)
            if not _values.is_missing(value):
                yield index, value


class CsvSource:
    """A data source over a delimited text file.

    CSV has exactly one type: string. Without the contract's declared types,
    every numeric or boolean feature would fail against every CSV, so this
    adapter uses the contract to parse each column into the type it is supposed
    to hold. A field that cannot be parsed is kept as its original text, which
    makes the column mixed and produces a type violation naming the actual
    offending value — more useful than a silent coercion to null.

    An empty field is read as null. That is a genuine judgement call: an empty
    CSV field is ambiguous between "missing" and "the empty string". Missing is
    overwhelmingly the common intent, and a feature that really does permit
    empty strings can express that with ``allowed_values``.

    Args:
        path: The file to read.
        contract: Supplies the types the file itself cannot carry.
        delimiter: Field separator.
        encoding: Text encoding.
    """

    def __init__(
        self,
        path: Path | str,
        contract: Contract,
        *,
        delimiter: str = ",",
        encoding: str = "utf-8-sig",
    ) -> None:
        self._path = Path(path)
        self._rows: list[dict[str, Any]] = []
        self._columns: tuple[str, ...] = ()

        with self._path.open(newline="", encoding=encoding) as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            self._columns = tuple(reader.fieldnames or ())
            for raw in reader:
                self._rows.append(
                    {name: _parse(raw.get(name), contract, name) for name in self._columns}
                )

    def describe(self) -> str:
        """Return the file name, so reports say which file failed."""
        return self._path.name

    def column_names(self) -> tuple[str, ...]:
        """Return the header row, in file order."""
        return self._columns

    def row_count(self) -> int:
        """Return the number of data rows, excluding the header."""
        return len(self._rows)

    def observed_dtype(self, column: str) -> DType | None:
        """Infer the column's type after parsing, or None if parsing was mixed."""
        return _values.infer(row.get(column) for row in self._rows)

    def null_count(self, column: str) -> int:
        """Count empty fields."""
        return sum(1 for row in self._rows if _values.is_missing(row.get(column)))

    def iter_values(self, column: str) -> Iterator[tuple[int, Any]]:
        """Yield ``(row_index, value)`` for every non-empty field."""
        for index, row in enumerate(self._rows):
            value = row.get(column)
            if not _values.is_missing(value):
                yield index, value


def _parse(raw: str | None, contract: Contract, column: str) -> Any:
    """Parse one CSV field using the contract's declared type for that column."""
    if raw is None or raw == "":
        return None

    feature = contract.get(column)
    if feature is None:
        # Undeclared column. The engine reports it separately; leave it as text
        # rather than guessing at a type nobody asked for.
        return raw

    succeeded, value = _values.coerce(raw, feature.dtype)
    return value if succeeded else raw
