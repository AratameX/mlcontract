"""The contract domain model.

A :class:`Contract` is an immutable, versioned description of the data an ML
component expects. A :class:`Feature` describes one field within it.

Both are validated at construction. An object that exists is a valid contract —
there is no half-built state where ``min`` exceeds ``max`` or a regex fails to
compile. Problems surface at the point of definition, with the offending field
named, rather than deep inside a validation run against a million rows.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlcontract import serialization
from mlcontract.constraints import CONSTRAINTS
from mlcontract.dtypes import DType
from mlcontract.exceptions import (
    MLC001,
    MLC002,
    MLC003,
    MLC004,
    MLC005,
    MLC007,
    MLC008,
    MLC009,
    MLC010,
    MLC011,
    MLC012,
    MLC013,
    MLC014,
    ContractDefinitionError,
)

SPEC_VERSION = "1"
"""The contract *file format* version written by this release.

Distinct from a contract's own ``version``, which the user owns and bumps as
their data evolves. This one is owned by the library and changes only when the
format itself does. Separating them is what makes it possible to evolve the
format later without invalidating every contract already committed to a repo.
"""

SUPPORTED_SPEC_VERSIONS = frozenset({"1"})
"""Format versions this release can read."""

_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

_FEATURE_KEYS = frozenset(
    {
        "type",
        "nullable",
        "required",
        "description",
        "previous_names",
        *CONSTRAINTS,
    }
)

_CONTRACT_KEYS = frozenset(
    {
        "spec_version",
        "name",
        "version",
        "description",
        "features",
        "enforce_column_order",
        "allow_extra_columns",
        "min_rows",
        "max_rows",
        "metadata",
    }
)


@dataclass(frozen=True, slots=True)
class Feature:
    """One field in a contract, with the rules its values must satisfy.

    Args:
        name: The column or key this feature refers to.
        dtype: Its canonical type. The annotation is
            :class:`~mlcontract.dtypes.DType` so that typed callers get
            autocompletion and are steered to the canonical set. At runtime any
            alias understood by :meth:`~mlcontract.dtypes.DType.parse` is also
            accepted, which is how strings arriving from contract files are
            handled.
        nullable: Whether null values are permitted at all.
        required: Whether the field must be present. An absent optional feature
            is fine; an absent required one is a violation.
        min: Smallest permitted value, inclusive. Numeric types only.
        max: Largest permitted value, inclusive. Numeric types only.
        allowed_values: The complete permitted domain. Discrete types only.
        pattern: A regular expression every value must match. Text types only.
        unique: Whether duplicate values are rejected.
        max_null_fraction: Largest permitted proportion of nulls, from 0 to 1.
            Only meaningful when ``nullable`` is True.
        description: Human-readable notes. Never affects validation.
        previous_names: Names this feature used to have. Renames are declared,
            never inferred — see :meth:`Contract.diff`.

    Raises:
        ContractDefinitionError: If any argument is invalid, if a constraint
            does not apply to the given type, or if two constraints contradict
            each other.

    Example:
        >>> Feature("age", DType.INTEGER, nullable=False, min=18, max=120)
        Feature(name='age', dtype=integer, required=True, nullable=False)
    """

    name: str
    dtype: DType
    nullable: bool = True
    required: bool = True
    min: float | None = None
    max: float | None = None
    allowed_values: Sequence[Any] | None = None
    pattern: str | None = None
    unique: bool = False
    max_null_fraction: float | None = None
    description: str | None = None
    previous_names: Sequence[str] = ()

    def __post_init__(self) -> None:
        """Normalise loose input, then reject anything incoherent."""
        # Accept the shapes callers naturally reach for — a type alias string, a
        # list of allowed values — and store the canonical, immutable form.
        object.__setattr__(self, "dtype", DType.parse(self.dtype))
        if self.allowed_values is not None:
            object.__setattr__(self, "allowed_values", tuple(self.allowed_values))
        object.__setattr__(self, "previous_names", tuple(self.previous_names))

        self._check_name()
        self._check_applicability()
        self._check_bounds()
        self._check_allowed_values()
        self._check_pattern()
        self._check_null_fraction()
        self._check_previous_names()

    def __repr__(self) -> str:
        """Return a short representation showing only the identifying fields."""
        return (
            f"Feature(name={self.name!r}, dtype={self.dtype}, "
            f"required={self.required}, nullable={self.nullable})"
        )

    def declared_constraints(self) -> dict[str, Any]:
        """Return the constraints this feature actually sets.

        Returns:
            Constraint names mapped to their values, omitting any left at the
            default. Used by serialisation to keep files free of noise, and by
            the diff engine to compare only what was declared.
        """
        declared: dict[str, Any] = {}
        for name in CONSTRAINTS:
            value = getattr(self, name)
            if _is_declared(value):
                declared[name] = value
        return declared

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical dictionary form of this feature.

        Keys left at their default are omitted, so a serialised contract shows
        only what its author actually decided.
        """
        data: dict[str, Any] = {"type": self.dtype.value}
        if not self.nullable:
            data["nullable"] = False
        if not self.required:
            data["required"] = False
        for key, value in self.declared_constraints().items():
            data[key] = list(value) if isinstance(value, tuple) else value
        if self.description is not None:
            data["description"] = self.description
        if self.previous_names:
            data["previous_names"] = list(self.previous_names)
        return data

    @classmethod
    def from_dict(cls, name: str, data: Mapping[str, Any]) -> Feature:
        """Build a feature from its dictionary form.

        Args:
            name: The feature name, which is the key in the contract's
                ``features`` mapping rather than a field of ``data``.
            data: The feature body.

        Returns:
            The feature.

        Raises:
            ContractDefinitionError: If a key is unrecognised or a value is
                invalid. Unknown keys suggest the closest valid spelling, since
                the usual cause is a typo.
        """
        _require_mapping(data, where=f"feature {name!r}")
        _reject_unknown_keys(data, _FEATURE_KEYS, where=f"feature {name!r}")

        if "type" not in data:
            raise ContractDefinitionError(
                f"Feature {name!r} does not declare a type.",
                code=MLC011,
                feature=name,
            )

        return cls(
            name=name,
            dtype=DType.parse(data["type"]),
            nullable=bool(data.get("nullable", True)),
            required=bool(data.get("required", True)),
            min=data.get("min"),
            max=data.get("max"),
            allowed_values=data.get("allowed_values"),
            pattern=data.get("pattern"),
            unique=bool(data.get("unique", False)),
            max_null_fraction=data.get("max_null_fraction"),
            description=data.get("description"),
            previous_names=tuple(data.get("previous_names", ())),
        )

    # -- validation ------------------------------------------------------

    def _check_name(self) -> None:
        if not _is_nonempty_str(self.name):
            raise ContractDefinitionError(
                f"Feature names must be non-empty strings, got {self.name!r}.",
                code=MLC001,
                feature=self.name,
            )

    def _check_applicability(self) -> None:
        for name, spec in CONSTRAINTS.items():
            if not _is_declared(getattr(self, name)):
                continue
            if not spec.accepts(self.dtype):
                permitted = ", ".join(sorted(str(d) for d in spec.applies_to))
                raise ContractDefinitionError(
                    f"Feature {self.name!r} is of type {self.dtype} and cannot use the "
                    f"{name!r} constraint, which applies to: {permitted}.",
                    code=MLC008,
                    feature=self.name,
                    constraint=name,
                    dtype=str(self.dtype),
                )

    def _check_bounds(self) -> None:
        for bound in ("min", "max"):
            value = getattr(self, bound)
            if value is not None and not _is_real_number(value):
                raise ContractDefinitionError(
                    f"Feature {self.name!r} has a non-numeric {bound!r} bound: {value!r}.",
                    code=MLC007,
                    feature=self.name,
                    constraint=bound,
                )

        if self.min is not None and self.max is not None and self.min > self.max:
            raise ContractDefinitionError(
                f"Feature {self.name!r} has min={self.min} greater than max={self.max}, "
                "so no value could ever satisfy it.",
                code=MLC009,
                feature=self.name,
                min=self.min,
                max=self.max,
            )

    def _check_allowed_values(self) -> None:
        if self.allowed_values is None:
            return

        if not self.allowed_values:
            raise ContractDefinitionError(
                f"Feature {self.name!r} declares an empty allowed_values set, so no value "
                "could ever satisfy it. Omit the constraint to allow any value.",
                code=MLC007,
                feature=self.name,
            )

        duplicates = _duplicates(self.allowed_values)
        if duplicates:
            raise ContractDefinitionError(
                f"Feature {self.name!r} lists duplicate allowed values: "
                f"{sorted(map(str, duplicates))}.",
                code=MLC007,
                feature=self.name,
                duplicates=sorted(map(str, duplicates)),
            )

        for value in self.allowed_values:
            if not _matches_dtype(value, self.dtype):
                raise ContractDefinitionError(
                    f"Feature {self.name!r} is of type {self.dtype} but allows the value "
                    f"{value!r}, which is a {type(value).__name__}.",
                    code=MLC007,
                    feature=self.name,
                    value=value,
                )

    def _check_pattern(self) -> None:
        if self.pattern is None:
            return
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ContractDefinitionError(
                f"Feature {self.name!r} has an invalid regular expression {self.pattern!r}: {exc}.",
                code=MLC007,
                feature=self.name,
                pattern=self.pattern,
            ) from exc

    def _check_null_fraction(self) -> None:
        if self.max_null_fraction is None:
            return

        if not _is_real_number(self.max_null_fraction) or not 0 <= self.max_null_fraction <= 1:
            raise ContractDefinitionError(
                f"Feature {self.name!r} has max_null_fraction={self.max_null_fraction!r}, "
                "which must be a number between 0 and 1.",
                code=MLC007,
                feature=self.name,
            )

        if not self.nullable and self.max_null_fraction > 0:
            raise ContractDefinitionError(
                f"Feature {self.name!r} is not nullable but permits a null fraction of "
                f"{self.max_null_fraction}. Set nullable=True, or drop max_null_fraction.",
                code=MLC009,
                feature=self.name,
            )

    def _check_previous_names(self) -> None:
        if self.name in self.previous_names:
            raise ContractDefinitionError(
                f"Feature {self.name!r} lists its own name among previous_names.",
                code=MLC013,
                feature=self.name,
            )
        duplicates = _duplicates(self.previous_names)
        if duplicates:
            raise ContractDefinitionError(
                f"Feature {self.name!r} repeats {sorted(duplicates)} in previous_names.",
                code=MLC013,
                feature=self.name,
            )


@dataclass(frozen=True, slots=True)
class Contract:
    """A versioned description of the data an ML component expects.

    Args:
        name: Identifies the contract. Stable across versions.
        version: The contract's own semantic version, owned by its author.
        features: The fields described, in declaration order. That order is what
            ``enforce_column_order`` checks against.
        description: Human-readable notes.
        enforce_column_order: Whether columns must appear in declaration order.
            Off by default — most consumers address columns by name, and
            enforcing order needlessly makes harmless reorderings fail.
        allow_extra_columns: Whether undeclared columns are tolerated. On by
            default, since data usually carries more than one model needs.
        min_rows: Fewest rows a dataset may contain.
        max_rows: Most rows a dataset may contain.
        metadata: Arbitrary user data, carried through serialisation untouched
            and never interpreted by this library.
        spec_version: The contract *format* version. Defaults to the current
            one; set only when reading an older file.

    Raises:
        ContractDefinitionError: If the contract is invalid in any way.

    Example:
        >>> contract = Contract(
        ...     name="customer_features",
        ...     version="1.0.0",
        ...     features=[
        ...         Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
        ...         Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US"]),
        ...     ],
        ... )
        >>> contract.feature_names
        ('age', 'country')
    """

    name: str
    version: str
    features: Sequence[Feature]
    description: str | None = None
    enforce_column_order: bool = False
    allow_extra_columns: bool = True
    min_rows: int | None = None
    max_rows: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    spec_version: str = SPEC_VERSION

    def __post_init__(self) -> None:
        """Normalise loose input, then reject anything incoherent."""
        object.__setattr__(self, "features", tuple(self.features))
        object.__setattr__(self, "metadata", dict(self.metadata))

        self._check_name()
        self._check_version()
        self._check_spec_version()
        self._check_features()
        self._check_row_bounds()

    def __repr__(self) -> str:
        """Return a short representation naming the contract and its size."""
        return (
            f"Contract(name={self.name!r}, version={self.version!r}, features={len(self.features)})"
        )

    def __iter__(self) -> Iterator[Feature]:
        """Iterate over features in declaration order."""
        return iter(self.features)

    def __len__(self) -> int:
        """Return the number of features."""
        return len(self.features)

    def __contains__(self, name: object) -> bool:
        """Return True if a feature with this name is declared."""
        return name in self._by_name()

    def __getitem__(self, name: str) -> Feature:
        """Return a feature by name.

        Raises:
            KeyError: If no such feature is declared.
        """
        try:
            return self._by_name()[name]
        except KeyError:
            raise KeyError(f"Contract {self.name!r} has no feature named {name!r}") from None

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return feature names in declaration order."""
        return tuple(feature.name for feature in self.features)

    @property
    def required_features(self) -> tuple[Feature, ...]:
        """Return only the features that must be present."""
        return tuple(feature for feature in self.features if feature.required)

    def get(self, name: str) -> Feature | None:
        """Return a feature by name, or None if it is not declared."""
        return self._by_name().get(name)

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical dictionary form of this contract.

        This is *the* representation. JSON and YAML are encodings of it, so both
        formats round-trip through this single code path and can never diverge.

        Returns:
            A plain dictionary of JSON-compatible types, with defaults omitted.
        """
        data: dict[str, Any] = {
            "spec_version": self.spec_version,
            "name": self.name,
            "version": self.version,
        }
        if self.description is not None:
            data["description"] = self.description
        if self.enforce_column_order:
            data["enforce_column_order"] = True
        if not self.allow_extra_columns:
            data["allow_extra_columns"] = False
        if self.min_rows is not None:
            data["min_rows"] = self.min_rows
        if self.max_rows is not None:
            data["max_rows"] = self.max_rows

        data["features"] = {feature.name: feature.to_dict() for feature in self.features}

        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Contract:
        """Build a contract from its dictionary form.

        Args:
            data: The contract document.

        Returns:
            The contract.

        Raises:
            ContractDefinitionError: If the document is malformed, uses an
                unsupported format version, or describes an invalid contract.
        """
        _require_mapping(data, where="contract")
        _reject_unknown_keys(data, _CONTRACT_KEYS, where="contract")

        for required in ("name", "version", "features"):
            if required not in data:
                raise ContractDefinitionError(
                    f"Contract document is missing the required key {required!r}.",
                    code=MLC011,
                    key=required,
                )

        raw_features = data["features"]
        _require_mapping(raw_features, where="the 'features' section")

        return cls(
            name=data["name"],
            version=data["version"],
            features=tuple(Feature.from_dict(name, body) for name, body in raw_features.items()),
            description=data.get("description"),
            enforce_column_order=bool(data.get("enforce_column_order", False)),
            allow_extra_columns=bool(data.get("allow_extra_columns", True)),
            min_rows=data.get("min_rows"),
            max_rows=data.get("max_rows"),
            metadata=data.get("metadata") or {},
            spec_version=str(data.get("spec_version", SPEC_VERSION)),
        )

    def to_json(self, *, indent: int = 2) -> str:
        """Render this contract as JSON text."""
        return serialization.encode_json(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> Contract:
        """Parse a contract from JSON text."""
        return cls.from_dict(_as_document(serialization.decode_json(text)))

    def to_yaml(self) -> str:
        """Render this contract as YAML text.

        Raises:
            IntegrationError: If PyYAML is not installed.
        """
        return serialization.encode_yaml(self.to_dict())

    @classmethod
    def from_yaml(cls, text: str) -> Contract:
        """Parse a contract from YAML text.

        Raises:
            IntegrationError: If PyYAML is not installed.
        """
        return cls.from_dict(_as_document(serialization.decode_yaml(text)))

    @classmethod
    def load(cls, path: Path | str) -> Contract:
        """Read a contract from a file, choosing the format by extension.

        Args:
            path: A ``.json``, ``.yaml`` or ``.yml`` file.

        Returns:
            The contract.

        Raises:
            ContractDefinitionError: If the file is missing, has an unrecognised
                extension, or does not contain a valid contract.
            IntegrationError: If the file is YAML and PyYAML is not installed.
        """
        location = Path(path)
        try:
            text = location.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContractDefinitionError(
                f"Could not read contract file {location}: {exc.strerror or exc}.",
                code=MLC010,
                path=str(location),
            ) from exc

        return cls.from_dict(_as_document(serialization.decode_text(text, path=location)))

    def save(self, path: Path | str) -> Path:
        """Write this contract to a file, choosing the format by extension.

        Args:
            path: Destination, ending in ``.json``, ``.yaml`` or ``.yml``.

        Returns:
            The path written to.

        Raises:
            ContractDefinitionError: If the extension is not recognised.
            IntegrationError: If the target is YAML and PyYAML is not installed.
        """
        location = Path(path)
        location.write_text(
            serialization.encode_for_path(self.to_dict(), location), encoding="utf-8"
        )
        return location

    # -- validation ------------------------------------------------------

    def _by_name(self) -> dict[str, Feature]:
        return {feature.name: feature for feature in self.features}

    def _check_name(self) -> None:
        if not _is_nonempty_str(self.name):
            raise ContractDefinitionError(
                f"Contract names must be non-empty strings, got {self.name!r}.",
                code=MLC001,
                name=self.name,
            )

    def _check_version(self) -> None:
        if not _is_semver(self.version):
            raise ContractDefinitionError(
                f"Contract {self.name!r} has version {self.version!r}, which is not a valid "
                "semantic version. Use MAJOR.MINOR.PATCH, for example '1.0.0'.",
                code=MLC004,
                version=self.version,
            )

    def _check_spec_version(self) -> None:
        if self.spec_version not in SUPPORTED_SPEC_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_SPEC_VERSIONS))
            raise ContractDefinitionError(
                f"Contract {self.name!r} declares format version {self.spec_version!r}, which "
                f"this release of mlcontract cannot read. Supported: {supported}. "
                "Upgrade mlcontract to read newer contracts.",
                code=MLC003,
                spec_version=self.spec_version,
            )

    def _check_features(self) -> None:
        if not self.features:
            raise ContractDefinitionError(
                f"Contract {self.name!r} declares no features. A contract that describes "
                "nothing cannot validate anything.",
                code=MLC012,
                name=self.name,
            )

        for item in self.features:
            if not isinstance(item, Feature):
                raise ContractDefinitionError(
                    f"Contract {self.name!r} contains {item!r}, which is not a Feature.",
                    code=MLC010,
                    name=self.name,
                )

        names = self.feature_names
        duplicates = _duplicates(names)
        if duplicates:
            raise ContractDefinitionError(
                f"Contract {self.name!r} declares duplicate feature names: {sorted(duplicates)}.",
                code=MLC005,
                duplicates=sorted(duplicates),
            )

        current = set(names)
        for item in self.features:
            collisions = current.intersection(item.previous_names)
            if collisions:
                raise ContractDefinitionError(
                    f"Feature {item.name!r} lists {sorted(collisions)} as previous names, but "
                    "those are still live features in this contract. A rename cannot point at "
                    "a name that still exists.",
                    code=MLC013,
                    feature=item.name,
                    collisions=sorted(collisions),
                )

    def _check_row_bounds(self) -> None:
        for bound in ("min_rows", "max_rows"):
            value = getattr(self, bound)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContractDefinitionError(
                    f"Contract {self.name!r} has {bound}={value!r}, which must be a "
                    "non-negative integer.",
                    code=MLC014,
                    bound=bound,
                    value=value,
                )

        if (
            self.min_rows is not None
            and self.max_rows is not None
            and self.min_rows > self.max_rows
        ):
            raise ContractDefinitionError(
                f"Contract {self.name!r} has min_rows={self.min_rows} greater than "
                f"max_rows={self.max_rows}, so no dataset could ever satisfy it.",
                code=MLC014,
                min_rows=self.min_rows,
                max_rows=self.max_rows,
            )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _as_document(value: Any) -> Mapping[str, Any]:
    """Narrow a decoded document to a mapping, with a useful error if it is not."""
    _require_mapping(value, where="contract document")
    assert isinstance(value, Mapping)
    return value


def _require_mapping(value: Any, *, where: str) -> None:
    """Raise unless ``value`` is a mapping."""
    if not isinstance(value, Mapping):
        raise ContractDefinitionError(
            f"Expected {where} to be a mapping of keys to values, got {type(value).__name__}.",
            code=MLC010,
            where=where,
        )


def _reject_unknown_keys(data: Mapping[str, Any], permitted: Iterable[str], *, where: str) -> None:
    """Raise on any key outside ``permitted``, suggesting the closest match.

    Silently ignoring unknown keys is how a misspelled ``nullabe: false`` ends up
    being quietly dropped, leaving a contract that looks stricter than it is.
    """
    allowed = frozenset(permitted)
    unknown = [key for key in data if key not in allowed]
    if not unknown:
        return

    key = unknown[0]
    suggestions = difflib.get_close_matches(str(key), sorted(allowed), n=1)
    hint = f" Did you mean {suggestions[0]!r}?" if suggestions else ""
    raise ContractDefinitionError(
        f"Unrecognised key {key!r} in {where}.{hint} Permitted keys: {', '.join(sorted(allowed))}.",
        code=MLC002,
        key=key,
        where=where,
    )


def _duplicates(values: Sequence[Any]) -> set[Any]:
    """Return values appearing more than once, ignoring unhashable entries."""
    seen: set[Any] = set()
    repeated: set[Any] = set()
    for value in values:
        try:
            if value in seen:
                repeated.add(value)
            else:
                seen.add(value)
        except TypeError:  # pragma: no cover - unhashable values are rejected earlier
            continue
    return repeated


def _is_declared(value: object) -> bool:
    """Return True if a constraint was actually set by the contract's author.

    Compares by identity, not equality. ``value in (None, False)`` looks
    equivalent and is not: ``0 == False`` in Python, so that form silently
    treats ``min=0`` and ``max_null_fraction=0.0`` as undeclared — dropping them
    from serialised contracts and skipping their validation entirely.
    """
    return value is not None and value is not False


def _is_nonempty_str(value: object) -> bool:
    """Return True for a string with at least one non-whitespace character.

    Takes ``object`` rather than ``str`` on purpose. The annotations on the
    public API promise ``str``, but nothing stops a caller passing an integer or
    a parsed document handing us ``None``, and a validation library that dies
    with ``AttributeError`` instead of a coded error has failed at its own job.
    Widening the parameter here keeps the runtime check meaningful without
    weakening the types users see.
    """
    return isinstance(value, str) and bool(value.strip())


def _is_semver(value: object) -> bool:
    """Return True if ``value`` is a string in MAJOR.MINOR.PATCH form."""
    return isinstance(value, str) and _SEMVER.match(value) is not None


def _is_real_number(value: Any) -> bool:
    """Return True for ints and floats, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _matches_dtype(value: Any, dtype: DType) -> bool:
    """Return True if a literal value is compatible with a canonical type.

    Only ever called for types that permit ``allowed_values``, which excludes
    ``FLOAT`` — enumerating exact floats invites equality-comparison bugs, so the
    constraint does not apply to continuous types at all.
    """
    if dtype is DType.BOOLEAN:
        return isinstance(value, bool)
    if dtype is DType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, str)
