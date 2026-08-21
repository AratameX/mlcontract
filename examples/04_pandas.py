"""Validate a pandas DataFrame.

Requires the pandas extra:

    pip install "schemapact[pandas]"
    python examples/04_pandas.py
"""

from __future__ import annotations

import sys

from schemapact import Contract, DType, Feature


def main() -> int:
    """Validate a DataFrame, including pandas' integer-to-float promotion."""
    try:
        import pandas as pd
    except ImportError:
        print('This example needs pandas:  pip install "schemapact[pandas]"')
        return 0

    contract = Contract(
        name="customer_features",
        version="1.0.0",
        features=[
            Feature("customer_id", DType.INTEGER, nullable=False, unique=True),
            Feature("age", DType.INTEGER, min=18, max=120),
            Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
        ],
    )

    # `age` holds a null, so pandas stores this column as float64 even though
    # the values are integers. schemapact recognises that promotion and does not
    # report a spurious type violation.
    frame = pd.DataFrame(
        {
            "customer_id": [1, 2, 3],
            "age": [34, None, 51],
            "country": ["IN", "US", "UK"],
        }
    )
    print(f"pandas dtype of 'age': {frame['age'].dtype}")
    print(contract.validate(frame).summary())

    print("\n== a frame that genuinely fails ==")
    broken = pd.DataFrame(
        {
            "customer_id": [1, 1],
            "age": [16, 200],
            "country": ["FR", "IN"],
        }
    )
    print(contract.validate(broken).summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
