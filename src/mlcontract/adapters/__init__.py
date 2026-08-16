"""Choosing the right adapter for whatever the caller passed.

:func:`resolve` is the only place in the library that inspects the *kind* of
data it has been given. Everything downstream sees a
:class:`~mlcontract._protocols.DataSource` and nothing else.

Detection is by duck typing rather than ``isinstance`` against imported classes,
because importing pandas here to check for a DataFrame would drag the dependency
into the core and defeat the point of the protocol.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mlcontract.adapters.mapping import CsvSource, MappingSource
from mlcontract.exceptions import MLC902, ContractValidationError

if TYPE_CHECKING:
    from mlcontract._protocols import DataSource
    from mlcontract.contract import Contract

CSV_SUFFIXES = frozenset({".csv", ".tsv"})
"""File extensions handled by the built-in CSV adapter."""


def resolve(data: Any, contract: Contract) -> DataSource:
    """Return a data source for whatever the caller passed.

    Args:
        data: A list of mappings, a path to a CSV or TSV file, or any object
            already implementing the data-source protocol.
        contract: Needed by formats that carry no type information of their own.

    Returns:
        A data source the engine can validate.

    Raises:
        ContractValidationError: If the data is of a kind no adapter handles.
        IntegrationError: If the data looks like a DataFrame but the extra that
            would handle it is not installed.
    """
    if _is_data_source(data):
        return data  # type: ignore[no-any-return]

    if isinstance(data, (str, os.PathLike)):
        return _resolve_path(Path(data), contract)

    if _looks_like_a_dataframe(data):
        # Imported here, never at module scope, so the core install never pulls
        # pandas in. The extra's absence surfaces as install guidance rather
        # than an ImportError from somewhere unrelated.
        from mlcontract.adapters.pandas import PandasSource

        return PandasSource(data)

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        if all(isinstance(row, Mapping) for row in data):
            return MappingSource(data)
        raise ContractValidationError(
            "A sequence was passed, but not every item is a mapping. Rows must be "
            "dict-like, for example [{'age': 30}, {'age': 41}].",
            code=MLC902,
        )

    raise ContractValidationError(
        f"Cannot validate an object of type {type(data).__name__!r}. Supported inputs are "
        "a list of mappings, a path to a .csv or .tsv file, or a pandas DataFrame with "
        'the "pandas" extra installed.',
        code=MLC902,
        received=type(data).__name__,
    )


def _resolve_path(path: Path, contract: Contract) -> DataSource:
    """Build a source from a file path, choosing by extension."""
    if not path.exists():
        raise ContractValidationError(f"No such data file: {path}", code=MLC902, path=str(path))

    suffix = path.suffix.lower()
    if suffix not in CSV_SUFFIXES:
        supported = ", ".join(sorted(CSV_SUFFIXES))
        raise ContractValidationError(
            f"Cannot read {path.name}: unsupported extension {suffix!r}. "
            f"Supported data files: {supported}.",
            code=MLC902,
            path=str(path),
        )

    return CsvSource(path, contract, delimiter="\t" if suffix == ".tsv" else ",")


def _is_data_source(data: Any) -> bool:
    """Return True if the object already implements the protocol."""
    required = (
        "describe",
        "column_names",
        "row_count",
        "observed_dtype",
        "null_count",
        "iter_values",
    )
    return all(callable(getattr(data, name, None)) for name in required)


def _looks_like_a_dataframe(data: Any) -> bool:
    """Return True for DataFrame-shaped objects, without importing pandas."""
    return hasattr(data, "columns") and hasattr(data, "dtypes") and hasattr(data, "iloc")


__all__ = ["CsvSource", "MappingSource", "resolve"]
