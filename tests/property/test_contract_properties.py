"""Property-based tests for contract invariants.

Example-based tests check the cases we thought of. These check claims that must
hold for *every* contract, against contracts Hypothesis invents — including the
awkward ones nobody would write by hand.

The invariants here are the foundation everything later depends on. If
round-tripping is lossy, contract diffing compares the wrong things and
breaking-change detection is unsound.
"""

from __future__ import annotations

from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mlcontract import Contract, DType, Feature
from tests._support import requires_yaml

# Identifiers that are legal feature names and survive both encodings.
names = st.from_regex(r"\A[a-z][a-z0-9_]{0,20}\Z", fullmatch=True)

versions = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    st.integers(0, 99),
    st.integers(0, 99),
    st.integers(0, 99),
)

# Finite bounds only: NaN would make min <= max meaningless, and infinity does
# not survive a JSON round trip.
finite = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)


@st.composite
def features(draw: st.DrawFn) -> Feature:
    """Build a valid feature with constraints appropriate to its type."""
    name = draw(names)
    dtype = draw(st.sampled_from(list(DType)))
    nullable = draw(st.booleans())

    kwargs: dict[str, Any] = {}

    if dtype.is_numeric:
        low, high = sorted(draw(st.tuples(finite, finite)))
        if draw(st.booleans()):
            kwargs["min"] = low
        if draw(st.booleans()):
            kwargs["max"] = high

    if dtype in (DType.STRING, DType.CATEGORICAL):
        if draw(st.booleans()):
            kwargs["allowed_values"] = draw(st.lists(names, min_size=1, max_size=5, unique=True))
        if draw(st.booleans()):
            kwargs["pattern"] = r"^[a-z]+$"

    if nullable and draw(st.booleans()):
        kwargs["max_null_fraction"] = draw(st.floats(0, 1, allow_nan=False))

    return Feature(
        name=name,
        dtype=dtype,
        nullable=nullable,
        required=draw(st.booleans()),
        unique=draw(st.booleans()),
        description=draw(st.one_of(st.none(), names)),
        **kwargs,
    )


@st.composite
def contracts(draw: st.DrawFn) -> Contract:
    """Build a valid contract with uniquely named features."""
    drawn = draw(st.lists(features(), min_size=1, max_size=6))

    seen: dict[str, Feature] = {}
    for feature in drawn:
        seen.setdefault(feature.name, feature)

    bounds = draw(st.one_of(st.none(), st.tuples(st.integers(0, 1000), st.integers(0, 1000))))
    min_rows, max_rows = (None, None) if bounds is None else sorted(bounds)

    return Contract(
        name=draw(names),
        version=draw(versions),
        features=tuple(seen.values()),
        description=draw(st.one_of(st.none(), names)),
        enforce_column_order=draw(st.booleans()),
        allow_extra_columns=draw(st.booleans()),
        min_rows=min_rows,
        max_rows=max_rows,
        metadata=draw(st.dictionaries(names, names, max_size=3)),
    )


SETTINGS = settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])


@given(contracts())
@SETTINGS
def test_dict_round_trip_is_lossless(contract):
    assert Contract.from_dict(contract.to_dict()) == contract


@given(contracts())
@SETTINGS
def test_json_round_trip_is_lossless(contract):
    assert Contract.from_json(contract.to_json()) == contract


@given(contracts())
@SETTINGS
@requires_yaml
def test_yaml_round_trip_is_lossless(contract):
    assert Contract.from_yaml(contract.to_yaml()) == contract


@given(contracts())
@SETTINGS
@requires_yaml
def test_json_and_yaml_are_the_same_contract_system(contract):
    """The core guarantee: two encodings, one representation.

    Neither format may gain or lose information the other keeps.
    """
    assert Contract.from_json(contract.to_json()) == Contract.from_yaml(contract.to_yaml())


@given(contracts())
@SETTINGS
def test_serialisation_is_deterministic(contract):
    """Identical contracts must produce byte-identical output, or files churn."""
    assert contract.to_json() == Contract.from_json(contract.to_json()).to_json()


@given(contracts())
@SETTINGS
@requires_yaml
def test_feature_order_survives_every_encoding(contract):
    assert Contract.from_yaml(contract.to_yaml()).feature_names == contract.feature_names


@given(contracts())
@SETTINGS
def test_equality_implies_identical_serialisation(contract):
    assert Contract.from_dict(contract.to_dict()).to_dict() == contract.to_dict()
