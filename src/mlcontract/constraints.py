"""The catalogue of constraints a feature can carry.

Each constraint is described once, here, as data. Three separate parts of the
library read this table:

* :mod:`mlcontract.contract` — to reject constraints on types they cannot apply
  to, such as a regex pattern on a float.
* the validation engine — to know which check to run.
* the diff engine — to know whether a change relaxed or tightened a rule, which
  is what makes breaking-change detection possible.

Encoding it once means those three can never drift apart. Adding a constraint is
an entry here plus an implementation, not a hunt through three modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mlcontract.dtypes import DType


class Direction(Enum):
    """Which way a constraint's value moves when the rule gets looser.

    A rule that accepts strictly more data after a change is *relaxed*, and
    relaxing is never a backward-breaking change. Tightening always is.
    """

    HIGHER_IS_LOOSER = "higher_is_looser"
    """Raising the value accepts more data — as with ``max`` or ``max_null_fraction``."""

    LOWER_IS_LOOSER = "lower_is_looser"
    """Lowering the value accepts more data — as with ``min``."""

    WIDER_SET_IS_LOOSER = "wider_set_is_looser"
    """Adding members accepts more data — as with ``allowed_values``."""

    ABSENT_IS_LOOSER = "absent_is_looser"
    """Removing the rule entirely accepts more data — as with ``pattern`` or ``unique``."""


@dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """Metadata describing one constraint.

    Attributes:
        name: The attribute on :class:`~mlcontract.contract.Feature`, which is
            also the key used in serialised contracts.
        applies_to: Types the constraint is meaningful for. Empty means all.
        direction: How the value moves when the rule is relaxed.
        summary: One-line description used in documentation and error messages.
    """

    name: str
    applies_to: frozenset[DType]
    direction: Direction
    summary: str

    def accepts(self, dtype: DType) -> bool:
        """Return True if this constraint may be used with ``dtype``."""
        return not self.applies_to or dtype in self.applies_to


_ORDERED = frozenset({DType.INTEGER, DType.FLOAT})
_TEXT = frozenset({DType.STRING, DType.CATEGORICAL})
_DISCRETE = frozenset(
    {DType.INTEGER, DType.BOOLEAN, DType.STRING, DType.CATEGORICAL, DType.DATE, DType.DATETIME}
)

CONSTRAINTS: dict[str, ConstraintSpec] = {
    spec.name: spec
    for spec in (
        ConstraintSpec(
            name="min",
            applies_to=_ORDERED,
            direction=Direction.LOWER_IS_LOOSER,
            summary="Smallest permitted value, inclusive.",
        ),
        ConstraintSpec(
            name="max",
            applies_to=_ORDERED,
            direction=Direction.HIGHER_IS_LOOSER,
            summary="Largest permitted value, inclusive.",
        ),
        ConstraintSpec(
            name="allowed_values",
            applies_to=_DISCRETE,
            direction=Direction.WIDER_SET_IS_LOOSER,
            summary="The complete set of values this feature may take.",
        ),
        ConstraintSpec(
            name="pattern",
            applies_to=_TEXT,
            direction=Direction.ABSENT_IS_LOOSER,
            summary="Regular expression every value must match.",
        ),
        ConstraintSpec(
            name="unique",
            applies_to=frozenset(),
            direction=Direction.ABSENT_IS_LOOSER,
            summary="Whether duplicate values are rejected.",
        ),
        ConstraintSpec(
            name="max_null_fraction",
            applies_to=frozenset(),
            direction=Direction.HIGHER_IS_LOOSER,
            summary="Largest permitted proportion of nulls, between 0 and 1.",
        ),
    )
}
"""Every constraint a feature can declare, keyed by name."""

CONSTRAINT_NAMES: frozenset[str] = frozenset(CONSTRAINTS)
"""Constraint names, for fast membership tests during parsing."""
