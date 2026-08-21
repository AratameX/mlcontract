"""Comparing two versions of a contract.

Every other feature in this library answers "is this data valid?". This one
answers "will this change break the people downstream?" — which is the question
that actually causes production incidents, and the one a dataframe validator
cannot answer at all.

The classification rests on a single idea. A change is **backward compatible**
when every dataset that satisfied the old contract still satisfies the new one.
That is a property you can reason about mechanically, constraint by constraint:
loosening a rule can only admit more data, tightening it can only reject data
that previously passed.

Forward compatibility needs no second table. "Can the old contract read data
written for the new one?" is the same question with the arguments swapped, so it
is computed by diffing in reverse. One implementation, no possibility of the two
directions drifting apart. See :mod:`schemapact.compatibility`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from schemapact.constraints import CONSTRAINTS, Direction
from schemapact.contract import Contract, Feature


class ChangeKind(Enum):
    """What sort of change was made."""

    FEATURE_ADDED = "feature_added"
    FEATURE_REMOVED = "feature_removed"
    FEATURE_RENAMED = "feature_renamed"
    DTYPE_CHANGED = "dtype_changed"
    NULLABILITY_CHANGED = "nullability_changed"
    REQUIREMENT_CHANGED = "requirement_changed"
    CONSTRAINT_CHANGED = "constraint_changed"
    SETTING_CHANGED = "setting_changed"
    DESCRIPTION_CHANGED = "description_changed"
    METADATA_CHANGED = "metadata_changed"

    def __str__(self) -> str:
        """Return the wire value."""
        return self.value


class Impact(Enum):
    """Whether a change admits more data, less, or the same.

    The whole classification reduces to this. ``TIGHTENED`` means some dataset
    that used to pass now fails, which is precisely what "breaking" means.
    """

    RELAXED = "relaxed"
    """Accepts strictly more data than before. Never breaking."""

    TIGHTENED = "tightened"
    """Rejects data that previously passed. Breaking."""

    NEUTRAL = "neutral"
    """Changes nothing about which data is accepted, such as a description."""

    def __str__(self) -> str:
        """Return the wire value."""
        return self.value


class VersionBump(Enum):
    """The smallest semantic-version increment a set of changes requires."""

    NONE = "none"
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"

    def __str__(self) -> str:
        """Return the wire value."""
        return self.value


_BUMP_ORDER = {
    VersionBump.NONE: 0,
    VersionBump.PATCH: 1,
    VersionBump.MINOR: 2,
    VersionBump.MAJOR: 3,
}


@dataclass(frozen=True, slots=True)
class Change:
    """One difference between two contracts.

    Attributes:
        kind: What sort of change it is.
        impact: Whether it admits more data, less, or the same.
        description: A human-readable account of the change.
        feature: The feature affected, or None for contract-wide settings.
        attribute: The specific attribute, such as ``"min"`` or ``"nullable"``.
        before: The old value.
        after: The new value.
    """

    kind: ChangeKind
    impact: Impact
    description: str
    feature: str | None = None
    attribute: str | None = None
    before: Any = None
    after: Any = None

    @property
    def is_breaking(self) -> bool:
        """Return True if some dataset that used to pass would now fail."""
        return self.impact is Impact.TIGHTENED

    def __str__(self) -> str:
        """Return a single log-friendly line."""
        where = f"{self.feature}: " if self.feature else ""
        return f"[{self.impact}] {where}{self.description}"

    def to_dict(self) -> dict[str, Any]:
        """Return the dictionary form."""
        return {
            "kind": self.kind.value,
            "impact": self.impact.value,
            "description": self.description,
            "feature": self.feature,
            "attribute": self.attribute,
            "before": _plain(self.before),
            "after": _plain(self.after),
            "breaking": self.is_breaking,
        }


@dataclass(frozen=True, slots=True)
class ContractDiff:
    """Every difference between two versions of a contract.

    Direction matters: the diff describes moving *from* ``old`` *to* ``new``, and
    reversing them gives a different answer.

    Attributes:
        old: The earlier contract.
        new: The later contract.
        changes: Every difference found, in a stable order — contract settings
            first, then features in the new contract's declaration order.
    """

    old: Contract
    new: Contract
    changes: tuple[Change, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        """Return the number of changes."""
        return len(self.changes)

    def __iter__(self) -> Iterator[Change]:
        """Iterate over the changes."""
        return iter(self.changes)

    @property
    def is_empty(self) -> bool:
        """Return True if the contracts are equivalent."""
        return not self.changes

    @property
    def breaking_changes(self) -> tuple[Change, ...]:
        """Return only the changes that reject previously valid data."""
        return tuple(change for change in self.changes if change.is_breaking)

    @property
    def is_breaking(self) -> bool:
        """Return True if any change rejects previously valid data.

        This is the *backward* question specifically. For forward or full
        compatibility use
        :meth:`~schemapact.contract.Contract.is_compatible_with`, which handles
        direction explicitly.
        """
        return bool(self.breaking_changes)

    @property
    def required_bump(self) -> VersionBump:
        """Return the smallest semantic-version increment these changes require.

        Derived from the changes rather than asserted, so it cannot disagree
        with them: anything breaking is a major, anything that admits more data
        is a minor, and cosmetic edits are a patch.
        """
        highest = VersionBump.NONE
        for change in self.changes:
            if change.impact is Impact.TIGHTENED:
                bump = VersionBump.MAJOR
            elif change.impact is Impact.RELAXED:
                bump = VersionBump.MINOR
            else:
                bump = VersionBump.PATCH
            if _BUMP_ORDER[bump] > _BUMP_ORDER[highest]:
                highest = bump
        return highest

    @property
    def declared_bump(self) -> VersionBump:
        """Return the version increment the two contracts actually declare."""
        return _declared_bump(self.old.version, self.new.version)

    @property
    def is_version_bump_sufficient(self) -> bool:
        """Return True if the declared version increment covers the changes.

        The check worth putting in CI. A breaking change shipped as a patch
        release is how downstream consumers get broken by an upgrade they had
        every reason to believe was safe.
        """
        return _BUMP_ORDER[self.declared_bump] >= _BUMP_ORDER[self.required_bump]

    def summary(self) -> str:
        """Return a human-readable account of the differences."""
        header = (
            f"{self.old.name} {self.old.version} -> {self.new.version}: "
            f"{len(self.changes)} change(s)"
        )
        if self.is_empty:
            return f"{header}\nNo differences."

        lines = [
            header,
            f"Breaking: {len(self.breaking_changes)}. "
            f"Requires a {self.required_bump} version bump; "
            f"{self.declared_bump} declared.",
            "",
        ]
        lines.extend(f"  {change}" for change in self.changes)
        if not self.is_version_bump_sufficient:
            lines.append("")
            lines.append(
                f"  WARNING: version went {self.old.version} -> {self.new.version}, but these "
                f"changes require a {self.required_bump} bump."
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return the machine-readable form."""
        return {
            "contract": self.new.name,
            "from_version": self.old.version,
            "to_version": self.new.version,
            "breaking": self.is_breaking,
            "required_bump": self.required_bump.value,
            "declared_bump": self.declared_bump.value,
            "version_bump_sufficient": self.is_version_bump_sufficient,
            "changes": [change.to_dict() for change in self.changes],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Return the JSON form."""
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"


def compare(old: Contract, new: Contract) -> ContractDiff:
    """Compare two contracts, from ``old`` to ``new``.

    Args:
        old: The earlier contract.
        new: The later contract.

    Returns:
        Every difference, each classified by its effect on which data is
        accepted.
    """
    changes: list[Change] = []
    changes.extend(_compare_settings(old, new))
    changes.extend(_compare_features(old, new))
    return ContractDiff(old=old, new=new, changes=tuple(changes))


# --------------------------------------------------------------------------
# Contract-level settings
# --------------------------------------------------------------------------


def _compare_settings(old: Contract, new: Contract) -> list[Change]:
    """Compare everything that is not a feature."""
    changes: list[Change] = []

    if old.description != new.description:
        changes.append(
            Change(
                kind=ChangeKind.DESCRIPTION_CHANGED,
                impact=Impact.NEUTRAL,
                description="Contract description changed.",
                attribute="description",
                before=old.description,
                after=new.description,
            )
        )

    if dict(old.metadata) != dict(new.metadata):
        changes.append(
            Change(
                kind=ChangeKind.METADATA_CHANGED,
                impact=Impact.NEUTRAL,
                description="Contract metadata changed.",
                attribute="metadata",
                before=dict(old.metadata),
                after=dict(new.metadata),
            )
        )

    if old.enforce_column_order != new.enforce_column_order:
        tightened = new.enforce_column_order
        changes.append(
            Change(
                kind=ChangeKind.SETTING_CHANGED,
                impact=Impact.TIGHTENED if tightened else Impact.RELAXED,
                description=(
                    "Column order is now enforced, so data whose columns are in a different "
                    "order is no longer accepted."
                    if tightened
                    else "Column order is no longer enforced."
                ),
                attribute="enforce_column_order",
                before=old.enforce_column_order,
                after=new.enforce_column_order,
            )
        )

    if old.allow_extra_columns != new.allow_extra_columns:
        tightened = not new.allow_extra_columns
        changes.append(
            Change(
                kind=ChangeKind.SETTING_CHANGED,
                impact=Impact.TIGHTENED if tightened else Impact.RELAXED,
                description=(
                    "Undeclared columns are now rejected."
                    if tightened
                    else "Undeclared columns are now tolerated."
                ),
                attribute="allow_extra_columns",
                before=old.allow_extra_columns,
                after=new.allow_extra_columns,
            )
        )

    for attribute, direction in (
        ("min_rows", Direction.LOWER_IS_LOOSER),
        ("max_rows", Direction.HIGHER_IS_LOOSER),
    ):
        before = getattr(old, attribute)
        after = getattr(new, attribute)
        impact = _impact_of(direction, before, after)
        if impact is not None:
            changes.append(
                Change(
                    kind=ChangeKind.SETTING_CHANGED,
                    impact=impact,
                    description=f"{attribute} changed from {before!r} to {after!r}.",
                    attribute=attribute,
                    before=before,
                    after=after,
                )
            )

    return changes


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------


def _compare_features(old: Contract, new: Contract) -> list[Change]:
    """Compare the feature sets, resolving declared renames first."""
    changes: list[Change] = []

    old_names = set(old.feature_names)
    new_names = set(new.feature_names)

    # Renames are resolved before additions and removals, so a declared rename
    # is reported once as a rename rather than twice as an unrelated
    # removal-and-addition. Only *declared* renames count: inferring them from
    # similar names produces confident wrong answers, and a compatibility tool
    # that is confidently wrong is worse than one that admits ignorance.
    renamed_from: dict[str, str] = {}
    for feature in new.features:
        for previous in feature.previous_names:
            if previous in old_names and previous not in new_names:
                renamed_from[feature.name] = previous
                break

    for feature in new.features:
        if feature.name in renamed_from:
            previous = renamed_from[feature.name]
            changes.append(
                Change(
                    kind=ChangeKind.FEATURE_RENAMED,
                    # Breaking: existing data still carries the old column name,
                    # and validation matches on the current name only.
                    impact=Impact.TIGHTENED,
                    description=(
                        f"Feature renamed from {previous!r} to {feature.name!r}. Existing data "
                        f"still uses {previous!r}."
                    ),
                    feature=feature.name,
                    attribute="name",
                    before=previous,
                    after=feature.name,
                )
            )
            changes.extend(_compare_feature(old[previous], feature))
            continue

        if feature.name not in old_names:
            changes.append(
                Change(
                    kind=ChangeKind.FEATURE_ADDED,
                    # A required addition is breaking: data written for the old
                    # contract has no such column. An optional one is not.
                    impact=Impact.TIGHTENED if feature.required else Impact.RELAXED,
                    description=(
                        f"Required feature {feature.name!r} added. Existing data does not "
                        "contain it."
                        if feature.required
                        else f"Optional feature {feature.name!r} added."
                    ),
                    feature=feature.name,
                    before=None,
                    after=str(feature.dtype),
                )
            )
            continue

        changes.extend(_compare_feature(old[feature.name], feature))

    removed = old_names - new_names - set(renamed_from.values())
    for name in (n for n in old.feature_names if n in removed):
        changes.append(
            Change(
                kind=ChangeKind.FEATURE_REMOVED,
                # Removing a declaration stops checking a column; it never
                # rejects data that previously passed. Consumers reading that
                # column are a forward-compatibility question, which the reverse
                # diff answers.
                impact=Impact.RELAXED,
                description=f"Feature {name!r} removed.",
                feature=name,
                before=str(old[name].dtype),
                after=None,
            )
        )

    return changes


def _compare_feature(old: Feature, new: Feature) -> list[Change]:
    """Compare one feature against its counterpart."""
    changes: list[Change] = []

    if old.dtype is not new.dtype:
        widens = old.dtype.widens_to(new.dtype)
        changes.append(
            Change(
                kind=ChangeKind.DTYPE_CHANGED,
                impact=Impact.RELAXED if widens else Impact.TIGHTENED,
                description=(
                    f"Type widened from {old.dtype} to {new.dtype}."
                    if widens
                    else f"Type changed from {old.dtype} to {new.dtype}, which does not accept "
                    "everything the previous type did."
                ),
                feature=new.name,
                attribute="dtype",
                before=str(old.dtype),
                after=str(new.dtype),
            )
        )

    if old.nullable != new.nullable:
        tightened = not new.nullable
        changes.append(
            Change(
                kind=ChangeKind.NULLABILITY_CHANGED,
                impact=Impact.TIGHTENED if tightened else Impact.RELAXED,
                description=(
                    "Nulls are no longer permitted." if tightened else "Nulls are now permitted."
                ),
                feature=new.name,
                attribute="nullable",
                before=old.nullable,
                after=new.nullable,
            )
        )

    if old.required != new.required:
        tightened = new.required
        changes.append(
            Change(
                kind=ChangeKind.REQUIREMENT_CHANGED,
                impact=Impact.TIGHTENED if tightened else Impact.RELAXED,
                description=(
                    "Feature is now required." if tightened else "Feature is now optional."
                ),
                feature=new.name,
                attribute="required",
                before=old.required,
                after=new.required,
            )
        )

    for name, spec in CONSTRAINTS.items():
        before = getattr(old, name)
        after = getattr(new, name)
        impact = _impact_of(spec.direction, before, after)
        if impact is None:
            continue
        changes.append(
            Change(
                kind=ChangeKind.CONSTRAINT_CHANGED,
                impact=impact,
                description=_describe_constraint(name, before, after, impact),
                feature=new.name,
                attribute=name,
                before=before,
                after=after,
            )
        )

    if old.description != new.description:
        changes.append(
            Change(
                kind=ChangeKind.DESCRIPTION_CHANGED,
                impact=Impact.NEUTRAL,
                description="Description changed.",
                feature=new.name,
                attribute="description",
                before=old.description,
                after=new.description,
            )
        )

    return changes


# --------------------------------------------------------------------------
# Constraint comparison
# --------------------------------------------------------------------------


def _impact_of(direction: Direction, before: Any, after: Any) -> Impact | None:
    """Classify a constraint change, or return None if nothing changed.

    An absent constraint is the loosest possible setting under every direction:
    no minimum accepts any value, no pattern accepts any string. That single
    observation lets adding, removing and altering a constraint be handled by
    one comparison rather than three special cases.
    """
    before = _normalise(before)
    after = _normalise(after)

    if direction is Direction.WIDER_SET_IS_LOOSER and before is not None and after is not None:
        # allowed_values is a set of permitted values. The order it happens to
        # be written in carries no meaning, so reordering must not register as
        # a change and churn every downstream compatibility check.
        before, after = frozenset(before), frozenset(after)

    if before == after:
        return None
    if before is None:
        return Impact.TIGHTENED  # A rule appeared where there was none.
    if after is None:
        return Impact.RELAXED  # A rule disappeared.

    if direction is Direction.LOWER_IS_LOOSER:
        return Impact.RELAXED if after < before else Impact.TIGHTENED
    if direction is Direction.HIGHER_IS_LOOSER:
        return Impact.RELAXED if after > before else Impact.TIGHTENED
    if direction is Direction.WIDER_SET_IS_LOOSER:
        removed = set(before) - set(after)
        return Impact.TIGHTENED if removed else Impact.RELAXED

    # ABSENT_IS_LOOSER, and both are present but different. A changed regular
    # expression could in principle be more permissive, but proving that is
    # undecidable in general, so the conservative answer is the honest one.
    return Impact.TIGHTENED


def _normalise(value: Any) -> Any:
    """Treat "not set" spellings alike, so False and None both mean absent."""
    if value is None or value is False:
        return None
    return tuple(value) if isinstance(value, (list, tuple)) else value


def _describe_constraint(name: str, before: Any, after: Any, impact: Impact) -> str:
    """Describe a constraint change in terms of what data it affects."""
    verb = "relaxed" if impact is Impact.RELAXED else "tightened"

    if name == "allowed_values":
        old_set = set(before or ())
        new_set = set(after or ())
        removed = sorted(str(v) for v in old_set - new_set)
        added = sorted(str(v) for v in new_set - old_set)
        parts = []
        if removed:
            parts.append(f"no longer allows {removed}")
        if added:
            parts.append(f"now also allows {added}")
        # No third case: a change is only reported when the sets actually differ,
        # so at least one of the two lists above is non-empty.
        return f"Allowed values {verb}: {'; '.join(parts)}."

    if before is None:
        return f"Constraint {name!r} added ({after!r}), rejecting data that previously passed."
    if after is None:
        return f"Constraint {name!r} removed (was {before!r})."
    return f"Constraint {name!r} {verb} from {before!r} to {after!r}."


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------


def _declared_bump(old_version: str, new_version: str) -> VersionBump:
    """Return the increment implied by two semantic version strings."""
    old_parts = _release_of(old_version)
    new_parts = _release_of(new_version)

    if new_parts == old_parts:
        return VersionBump.NONE
    if new_parts[0] != old_parts[0]:
        return VersionBump.MAJOR
    if new_parts[1] != old_parts[1]:
        return VersionBump.MINOR
    return VersionBump.PATCH


def _release_of(version: str) -> tuple[int, int, int]:
    """Return the numeric release segment, ignoring pre-release and build parts."""
    core = version.split("+", 1)[0].split("-", 1)[0]
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch


def _plain(value: Any) -> Any:
    """Convert to JSON-safe types."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    return value
