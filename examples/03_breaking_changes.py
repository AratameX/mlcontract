"""Detect breaking changes between contract versions.

This is the part a dataframe validator cannot do: not "is this data valid?" but
"will this change break the people downstream?"

Run it:

    python examples/03_breaking_changes.py
"""

from __future__ import annotations

from mlcontract import Compatibility, Contract, DType, Feature

V1 = Contract(
    name="customer_features",
    version="1.0.0",
    features=[
        Feature("customer_id", DType.INTEGER, nullable=False),
        Feature("age", DType.INTEGER, min=18),
        Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
        Feature("legacy_score", DType.FLOAT),
    ],
)

V2 = Contract(
    name="customer_features",
    version="1.1.0",  # deliberately too small for what changed
    features=[
        Feature("customer_id", DType.INTEGER, nullable=False),
        Feature("age", DType.INTEGER, min=21),  # tightened: breaking
        Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK", "AU"]),
        Feature("email", DType.STRING),  # required addition: breaking
        # legacy_score removed: safe backward, breaks forward
    ],
)


def main() -> None:
    """Show the diff, then the same change judged in each direction."""
    changes = V1.diff(V2)

    print("== what changed ==")
    print(changes.summary())

    print(f"\nrequired bump: {changes.required_bump}")
    print(f"declared bump: {changes.declared_bump}")
    print(f"sufficient:    {changes.is_version_bump_sufficient}")

    # The same change, three questions. A single boolean cannot express this.
    print("\n== compatibility, by direction ==")
    for mode in Compatibility:
        result = V1.is_compatible_with(V2, mode)
        verdict = "compatible" if result.is_compatible else "INCOMPATIBLE"
        print(f"  {mode!s:<9} {verdict}")

    print("\n== why forward differs ==")
    print(V1.is_compatible_with(V2, Compatibility.FORWARD).summary())


if __name__ == "__main__":
    main()
