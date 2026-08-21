"""Validation throughput across backends and dataset sizes.

This is the number that matters. Contract loading happens once; validation
happens over every row, so it is the only part of the library whose performance
can plausibly stop someone using it.

Both adapters are measured on identical data so the comparison is meaningful.
The stdlib adapter is the honest floor — no third-party code, no vectorisation.
"""

from __future__ import annotations

import random
from functools import partial
from typing import Any

from benchmarks._harness import Suite, announce, measure
from schemapact import Contract, DType, Feature

SIZES: tuple[int, ...] = (1_000, 10_000, 100_000)

CONTRACT = Contract(
    name="benchmark_input",
    version="1.0.0",
    features=[
        Feature("id", DType.INTEGER, nullable=False),
        Feature("age", DType.INTEGER, nullable=False, min=0, max=120),
        Feature("score", DType.FLOAT, min=0.0, max=1.0),
        Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK", "AU"]),
        Feature("active", DType.BOOLEAN),
    ],
)


def make_rows(count: int, *, seed: int = 0) -> list[dict[str, Any]]:
    """Build deterministic clean data."""
    rng = random.Random(seed)
    countries = ["IN", "US", "UK", "AU"]
    return [
        {
            "id": index,
            "age": rng.randint(0, 120),
            "score": rng.random(),
            "country": rng.choice(countries),
            "active": rng.random() > 0.5,
        }
        for index in range(count)
    ]


def run(suite: Suite) -> None:
    """Measure validation across adapters and sizes."""
    announce("Validation throughput — stdlib adapter")
    for size in SIZES:
        rows = make_rows(size)
        suite.record(
            measure(
                f"validate list[dict] ({size:,} rows)",
                "validation",
                partial(CONTRACT.validate, rows, sample_values=False),
                iterations=5 if size >= 100_000 else 20,
                rows=size,
                notes="Pure standard library, no dependencies.",
            )
        )

    try:
        import pandas as pd
    except ImportError:
        print("  (pandas not installed; skipping DataFrame benchmarks)")
        return

    announce("Validation throughput — pandas adapter")
    for size in SIZES:
        frame = pd.DataFrame(make_rows(size))
        suite.record(
            measure(
                f"validate DataFrame ({size:,} rows)",
                "validation",
                partial(CONTRACT.validate, frame, sample_values=False),
                iterations=5 if size >= 100_000 else 20,
                rows=size,
                notes="Vectorised: value checks evaluate whole columns via the adapter.",
            )
        )

    announce("Effect of sampling failing values")
    dirty = make_rows(10_000)
    for row in dirty[::10]:
        row["age"] = 999  # 10% of rows violate the maximum

    for label, sampling in (("with samples", True), ("without samples", False)):
        suite.record(
            measure(
                f"validate 10,000 rows, 10% failing ({label})",
                "validation",
                partial(CONTRACT.validate, dirty, sample_values=sampling),
                iterations=20,
                rows=10_000,
            )
        )
