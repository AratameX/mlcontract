"""Validate a list of dictionaries — no dependencies beyond the standard library.

Run it:

    python examples/01_quickstart.py
"""

from __future__ import annotations

from mlcontract import Contract, DType, Feature


def main() -> None:
    """Define a contract, then check clean and dirty data against it."""
    contract = Contract(
        name="customer_features",
        version="1.0.0",
        features=[
            Feature("customer_id", DType.INTEGER, nullable=False, unique=True),
            Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
            Feature("lifetime_value", DType.FLOAT, min=0),
        ],
    )

    good = [
        {"customer_id": 1, "age": 34, "country": "IN", "lifetime_value": 240.5},
        {"customer_id": 2, "age": 51, "country": "US", "lifetime_value": 0.0},
    ]
    print("== clean data ==")
    print(contract.validate(good).summary())

    # Each row below breaks a different rule.
    bad = [
        {"customer_id": 1, "age": 16, "country": "IN", "lifetime_value": 10.0},
        {"customer_id": 1, "age": 45, "country": "FR", "lifetime_value": -5.0},
    ]
    report = contract.validate(bad)

    print("\n== dirty data ==")
    print(report.summary())

    print("\n== codes, for alerting ==")
    print(", ".join(report.codes()))


if __name__ == "__main__":
    main()
