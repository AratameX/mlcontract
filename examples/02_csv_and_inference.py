"""Infer a contract from a CSV, then validate against it.

Writing the first contract by hand is the main obstacle to getting started.
Reading one off a file you already have turns that into a starting point you
edit.

Run it:

    python examples/02_csv_and_inference.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from schemapact import Contract
from schemapact._inference import infer_from_csv

SAMPLE = """customer_id,age,country,lifetime_value
1,34,IN,240.50
2,51,US,0.00
3,29,UK,88.10
"""

LATER = """customer_id,age,country,lifetime_value
4,17,FR,-3.00
"""


def main() -> None:
    """Infer a contract from one file and validate a later one against it."""
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        (workspace / "sample.csv").write_text(SAMPLE, encoding="utf-8")
        (workspace / "later.csv").write_text(LATER, encoding="utf-8")

        contract = infer_from_csv(workspace / "sample.csv", name="customers")
        contract.save(workspace / "contract.json")

        print("== inferred contract ==")
        print(contract.to_json())

        # Types were inferred; ranges were not. A minimum read off three rows
        # would reject legitimate data the moment something smaller arrived.
        print("== inferred age constraints ==")
        print(f"dtype={contract['age'].dtype}  min={contract['age'].min}")

        print("\n== the sample validates against its own contract ==")
        print(contract.validate(workspace / "sample.csv").summary())

        print("\n== later data does not ==")
        tightened = Contract.from_dict(
            {
                **contract.to_dict(),
                "features": {
                    **contract.to_dict()["features"],
                    "age": {"type": "integer", "min": 18},
                    "lifetime_value": {"type": "float", "min": 0},
                },
            }
        )
        print(tightened.validate(workspace / "later.csv").summary())


if __name__ == "__main__":
    main()
