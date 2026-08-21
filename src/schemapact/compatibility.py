"""Directional compatibility between contract versions.

"Is this change breaking?" has no answer until you ask *for whom*. Adding a
required field breaks every system that writes the data and none of the systems
that read it. Removing a field is the reverse. A single boolean cannot express
that, and a tool that reports one is telling half its users the wrong thing.

So compatibility is asked in a direction:

:attr:`Compatibility.BACKWARD`
    Can the **new** contract read data written for the **old** one? This is what
    you want before deploying a new consumer against existing data.

:attr:`Compatibility.FORWARD`
    Can the **old** contract read data written for the **new** one? This is what
    you want before letting a producer upgrade while consumers lag behind.

:attr:`Compatibility.FULL`
    Both, which is what you need when producers and consumers upgrade
    independently and in no guaranteed order.

Only backward compatibility is implemented. Forward compatibility is backward
compatibility with the contracts swapped, so it is computed by reversing the
diff — one rule set, and no way for the two directions to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from schemapact.contract import Contract
from schemapact.diff import Change, compare
from schemapact.exceptions import SPX601, CompatibilityError


class Compatibility(Enum):
    """Which direction of compatibility to check."""

    BACKWARD = "backward"
    """The new contract accepts everything the old one did."""

    FORWARD = "forward"
    """The old contract accepts everything the new one does."""

    FULL = "full"
    """Both directions."""

    def __str__(self) -> str:
        """Return the wire value."""
        return self.value


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    """The outcome of a compatibility check.

    Deliberately not a bare boolean. When a check fails, the useful information
    is *which* changes caused it and in which direction, and a boolean throws all
    of that away at exactly the moment someone needs it.

    Attributes:
        mode: The direction that was checked.
        old: The earlier contract.
        new: The later contract.
        backward_breaking: Changes preventing the new contract from reading old
            data. Empty when backward compatibility was not checked.
        forward_breaking: Changes preventing the old contract from reading new
            data. Empty when forward compatibility was not checked.
    """

    mode: Compatibility
    old: Contract
    new: Contract
    backward_breaking: tuple[Change, ...] = field(default_factory=tuple)
    forward_breaking: tuple[Change, ...] = field(default_factory=tuple)

    @property
    def is_compatible(self) -> bool:
        """Return True if the change is safe in the direction that was checked."""
        return not self.backward_breaking and not self.forward_breaking

    @property
    def breaking_changes(self) -> tuple[Change, ...]:
        """Return every change that caused the check to fail."""
        return self.backward_breaking + self.forward_breaking

    def summary(self) -> str:
        """Return a human-readable account of the outcome."""
        header = (
            f"{self.new.name}: {self.old.version} -> {self.new.version}, {self.mode} compatibility"
        )
        if self.is_compatible:
            return f"{header}\nCOMPATIBLE."

        lines = [header, f"INCOMPATIBLE: {len(self.breaking_changes)} breaking change(s)", ""]
        if self.backward_breaking:
            lines.append("  The new contract cannot read data written for the old one:")
            lines.extend(f"    - {change}" for change in self.backward_breaking)
        if self.forward_breaking:
            if self.backward_breaking:
                lines.append("")
            lines.append(
                "  The old contract cannot read data written for the new one. These are "
                "stated as the reverse change, which is what makes them breaking:"
            )
            lines.extend(f"    - {change}" for change in self.forward_breaking)
        return "\n".join(lines)

    def raise_for_status(self) -> None:
        """Raise if the change is not compatible in the direction checked.

        For pipelines that want to fail immediately rather than inspect the
        result.

        Raises:
            CompatibilityError: If incompatible. Carries the full result.
        """
        if self.is_compatible:
            return
        raise CompatibilityError(
            f"{self.new.name} {self.old.version} -> {self.new.version} is not "
            f"{self.mode} compatible: {len(self.breaking_changes)} breaking change(s).\n"
            + self.summary(),
            code=SPX601,
            result=self,
            mode=self.mode.value,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the machine-readable form."""
        return {
            "contract": self.new.name,
            "from_version": self.old.version,
            "to_version": self.new.version,
            "mode": self.mode.value,
            "compatible": self.is_compatible,
            "backward_breaking": [change.to_dict() for change in self.backward_breaking],
            "forward_breaking": [change.to_dict() for change in self.forward_breaking],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Return the JSON form."""
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"


def check(
    old: Contract,
    new: Contract,
    mode: Compatibility = Compatibility.BACKWARD,
) -> CompatibilityResult:
    """Check whether moving from ``old`` to ``new`` is compatible.

    Args:
        old: The earlier contract.
        new: The later contract.
        mode: Which direction to check. Backward by default, since deploying a
            new contract against data that already exists is the common case.

    Returns:
        The outcome, including which changes broke it and in which direction.

    Example:
        >>> from schemapact import DType, Feature
        >>> old = Contract(
        ...     name="c", version="1.0.0",
        ...     features=[Feature("age", DType.INTEGER)],
        ... )
        >>> new = Contract(
        ...     name="c", version="2.0.0",
        ...     features=[Feature("age", DType.INTEGER), Feature("email", DType.STRING)],
        ... )
        >>> check(old, new, Compatibility.BACKWARD).is_compatible
        False
        >>> check(old, new, Compatibility.FORWARD).is_compatible
        True
    """
    backward: tuple[Change, ...] = ()
    forward: tuple[Change, ...] = ()

    if mode in (Compatibility.BACKWARD, Compatibility.FULL):
        backward = compare(old, new).breaking_changes

    if mode in (Compatibility.FORWARD, Compatibility.FULL):
        # Forward compatibility is backward compatibility with the arguments
        # swapped: "can the old contract read new data?" is "does new-to-old
        # tighten anything?". Reusing the same rules means the two directions
        # cannot drift apart as the classification table grows.
        forward = compare(new, old).breaking_changes

    return CompatibilityResult(
        mode=mode,
        old=old,
        new=new,
        backward_breaking=backward,
        forward_breaking=forward,
    )
