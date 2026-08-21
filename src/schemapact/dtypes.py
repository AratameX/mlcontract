"""The canonical type system contracts are written in.

Contracts describe data that may live in pandas, Polars, Arrow, a CSV file or a
list of dictionaries. Those backends disagree about type names, nullability and
integer widths, so contracts do not use any of their vocabularies. They use the
small canonical set defined here, and each adapter is responsible for mapping
its own types onto it.

Keeping this set deliberately small is a design decision, not an omission. Every
type added here must be mapped by every adapter, forever.
"""

from __future__ import annotations

from enum import Enum

from schemapact.exceptions import SPX006, ContractDefinitionError


class DType(Enum):
    """A canonical contract data type.

    Members are compared by identity and serialise to their lowercase string
    value, which is what appears in contract files.
    """

    INTEGER = "integer"
    """Whole numbers. Excludes booleans, which are their own type."""

    FLOAT = "float"
    """Real numbers, including NaN and infinity unless constrained otherwise."""

    BOOLEAN = "boolean"
    """True or false."""

    STRING = "string"
    """Free text, with no restriction on which values may appear."""

    CATEGORICAL = "categorical"
    """Text drawn from a known domain. Pair with ``allowed_values``."""

    DATETIME = "datetime"
    """A point in time, with or without a timezone."""

    DATE = "date"
    """A calendar date with no time component."""

    def __str__(self) -> str:
        """Return the wire value, e.g. ``"integer"``.

        Defined explicitly because the string behaviour of enum mixins changed
        between Python 3.10 and 3.12; this keeps output identical everywhere.
        """
        return self.value

    @property
    def is_numeric(self) -> bool:
        """Return True if ordering and arithmetic comparisons are meaningful."""
        return self in _NUMERIC

    @property
    def is_temporal(self) -> bool:
        """Return True for date and datetime types."""
        return self in _TEMPORAL

    @property
    def is_textual(self) -> bool:
        """Return True for types whose values are text."""
        return self in _TEXTUAL

    def widens_to(self, other: DType) -> bool:
        """Return True if every value of this type is also valid as ``other``.

        Widening is the basis of backward compatibility in :mod:`schemapact.diff`:
        a type change that widens accepts all previously valid data and is
        therefore not breaking, while any other change is.

        Args:
            other: The type being widened to.

        Returns:
            True if the change is a widening. A type always widens to itself.

        Example:
            >>> DType.INTEGER.widens_to(DType.FLOAT)
            True
            >>> DType.FLOAT.widens_to(DType.INTEGER)
            False
        """
        return self is other or (self, other) in _WIDENINGS

    def accepts(self, observed: DType) -> bool:
        """Return True if data observed as ``observed`` satisfies this declared type.

        This asks a different question from :meth:`widens_to`, and conflating the
        two is a real source of bugs, so they are separate methods.

        * :meth:`widens_to` is about *contract evolution*: may the declared type
          change from A to B without breaking existing data?
        * :meth:`accepts` is about *data conformance*: does a column that turned
          out to hold B satisfy a contract that declared A?

        They are not inverses and they are not the same relation. A column of
        plain strings satisfies a ``categorical`` declaration — membership of the
        allowed set is a separate check — yet ``string`` does not widen to
        ``categorical``, because narrowing a declaration to a fixed domain
        rejects data that was previously fine.

        Args:
            observed: The type the data actually turned out to have.

        Returns:
            True if the data conforms.

        Example:
            >>> DType.FLOAT.accepts(DType.INTEGER)
            True
            >>> DType.INTEGER.accepts(DType.FLOAT)
            False
            >>> DType.CATEGORICAL.accepts(DType.STRING)
            True
        """
        return self is observed or (observed, self) in _ACCEPTED

    @classmethod
    def parse(cls, value: str | DType) -> DType:
        """Resolve a type name, accepting common aliases.

        Args:
            value: A :class:`DType`, or a name such as ``"int64"`` or ``"str"``.

        Returns:
            The canonical type.

        Raises:
            ContractDefinitionError: If the name is not recognised. The message
                lists every accepted spelling.
        """
        if isinstance(value, cls):
            return value

        if not isinstance(value, str):
            raise ContractDefinitionError(
                f"Data type must be a string or DType, got {type(value).__name__}.",
                code=SPX006,
                value=value,
            )

        resolved = _ALIASES.get(value.strip().lower())
        if resolved is None:
            accepted = ", ".join(sorted(_ALIASES))
            raise ContractDefinitionError(
                f"Unknown data type {value!r}. Accepted names: {accepted}.",
                code=SPX006,
                value=value,
            )
        return resolved


_NUMERIC = frozenset({DType.INTEGER, DType.FLOAT})
_TEMPORAL = frozenset({DType.DATETIME, DType.DATE})
_TEXTUAL = frozenset({DType.STRING, DType.CATEGORICAL})

_WIDENINGS: frozenset[tuple[DType, DType]] = frozenset(
    {
        # Every integer is representable as a float.
        (DType.INTEGER, DType.FLOAT),
        # Dropping a domain restriction accepts strictly more values.
        (DType.CATEGORICAL, DType.STRING),
        # A date is a datetime at midnight.
        (DType.DATE, DType.DATETIME),
    }
)
"""Ordered pairs ``(from, to)`` where every value of ``from`` is valid as ``to``.

Deliberately conservative. ``INTEGER -> STRING`` is excluded even though any
integer can be rendered as text: the values survive but comparisons, ordering
and arithmetic do not, so downstream consumers break.
"""

_ACCEPTED: frozenset[tuple[DType, DType]] = frozenset(
    {
        # Integers satisfy a float declaration; the reverse loses precision.
        (DType.INTEGER, DType.FLOAT),
        # A categorical column is string-backed, so strings satisfy it. Whether
        # the values are in the allowed set is a separate constraint.
        (DType.STRING, DType.CATEGORICAL),
        (DType.CATEGORICAL, DType.STRING),
        # A date satisfies a datetime declaration at midnight.
        (DType.DATE, DType.DATETIME),
    }
)
"""Ordered pairs ``(observed, declared)`` where the observed data conforms."""

_ALIASES: dict[str, DType] = {
    # Canonical names.
    **{member.value: member for member in DType},
    # Python and NumPy spellings people reach for by habit.
    "int": DType.INTEGER,
    "int8": DType.INTEGER,
    "int16": DType.INTEGER,
    "int32": DType.INTEGER,
    "int64": DType.INTEGER,
    "long": DType.INTEGER,
    "double": DType.FLOAT,
    "float32": DType.FLOAT,
    "float64": DType.FLOAT,
    "number": DType.FLOAT,
    "bool": DType.BOOLEAN,
    "str": DType.STRING,
    "text": DType.STRING,
    "category": DType.CATEGORICAL,
    "enum": DType.CATEGORICAL,
    "timestamp": DType.DATETIME,
}
"""Accepted spellings, lowercased.

Note that ``object`` is intentionally absent. In pandas it means "anything at
all", so silently reading it as ``string`` would make a contract claim something
the data does not support. Adapters must resolve such types explicitly.
"""
