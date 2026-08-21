"""Fail a build when a contract change would break consumers.

The pattern this library exists for. Run it in CI on every pull request that
touches a contract, and an incompatible schema change becomes a red build
instead of a production incident.

Equivalent as a shell step:

    schemapact check-compatibility contracts/v1.yaml contracts/v2.yaml --mode backward

Run it:

    python examples/05_ci_gate.py
"""

from __future__ import annotations

import sys

from schemapact import Compatibility, Contract, DType, Feature

PRODUCTION = Contract(
    name="model_input",
    version="2.3.0",
    features=[
        Feature("user_id", DType.INTEGER, nullable=False),
        Feature("tenure_days", DType.INTEGER, min=0),
        Feature("plan", DType.CATEGORICAL, allowed_values=["free", "pro"]),
    ],
)

PROPOSED = Contract(
    name="model_input",
    version="2.4.0",
    features=[
        Feature("user_id", DType.INTEGER, nullable=False),
        Feature("tenure_days", DType.INTEGER, min=0),
        # A new plan tier: strictly more values, so existing data still passes.
        Feature("plan", DType.CATEGORICAL, allowed_values=["free", "pro", "team"]),
        # Optional, so producers that do not send it are still valid.
        Feature("referral_code", DType.STRING, required=False),
    ],
)


def gate(old: Contract, new: Contract, mode: Compatibility) -> int:
    """Return a process exit code for a proposed contract change."""
    result = old.is_compatible_with(new, mode)
    print(result.summary())

    if result.is_compatible:
        print("\nOK: safe to merge.")
        return 0

    print("\nFAILED: this change breaks existing consumers.")
    print("Either revert it, or bump the major version and coordinate the rollout.")
    return 1


def main() -> int:
    """Gate the proposed change, and show what a breaking one would look like."""
    print("== proposed change ==")
    code = gate(PRODUCTION, PROPOSED, Compatibility.BACKWARD)

    print("\n== a change that would be rejected ==")
    breaking = Contract.from_dict(
        {
            **PROPOSED.to_dict(),
            "version": "2.5.0",
            "features": {
                **PROPOSED.to_dict()["features"],
                "referral_code": {"type": "string"},  # now required
            },
        }
    )
    gate(PRODUCTION, breaking, Compatibility.BACKWARD)

    return code


if __name__ == "__main__":
    sys.exit(main())
