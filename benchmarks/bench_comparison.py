"""Honest comparison against the alternatives.

Two baselines, both doing exactly the same checks on exactly the same data:

**Hand-written pandas assertions** — what most teams actually have. It is the
floor any library must beat on usefulness, and it will usually win on raw speed,
because it does nothing but the comparisons while a contract library also builds
a structured report, counts affected rows and collects examples.

**Pandera**, when installed — the closest established alternative for dataframe
validation.

Where mlcontract loses, the results say so. A benchmark table where the author's
library wins every row is not evidence; it is marketing, and readers discount it
accordingly. The case for this library rests on contract versioning and
breaking-change detection, which neither baseline does at all.
"""

from __future__ import annotations

from benchmarks._harness import Suite, announce, measure
from benchmarks.bench_validation import CONTRACT, make_rows


def run(suite: Suite) -> None:
    """Compare against hand-written checks and, if present, Pandera."""
    try:
        import pandas as pd
    except ImportError:
        print("  (pandas not installed; skipping comparison benchmarks)")
        return

    announce("Comparison — same checks, same data, 100,000 rows")
    size = 100_000
    frame = pd.DataFrame(make_rows(size))
    group = "comparison"

    def hand_written() -> list[str]:
        """The checks a team writes by hand, with no structured output."""
        problems: list[str] = []
        if frame["id"].isna().any():
            problems.append("id has nulls")
        if not frame["age"].between(0, 120).all():
            problems.append("age out of range")
        if not frame["score"].between(0.0, 1.0).all():
            problems.append("score out of range")
        if not frame["country"].isin(["IN", "US", "UK", "AU"]).all():
            problems.append("unexpected country")
        return problems

    suite.record(
        measure(
            "hand-written pandas assertions",
            group,
            hand_written,
            iterations=10,
            rows=size,
            notes="Vectorised, but returns no codes, no row numbers and no examples.",
        )
    )

    suite.record(
        measure(
            "mlcontract, pandas adapter",
            group,
            lambda: CONTRACT.validate(frame, sample_values=False),
            iterations=5,
            rows=size,
            notes="Produces a structured report with codes and affected row counts.",
        )
    )

    try:
        import pandera.pandas as pa
    except ImportError:
        print("  (pandera not installed; skipping that comparison)")
        return

    schema = pa.DataFrameSchema(
        {
            "id": pa.Column(int, nullable=False),
            "age": pa.Column(int, pa.Check.in_range(0, 120)),
            "score": pa.Column(float, pa.Check.in_range(0.0, 1.0)),
            "country": pa.Column(str, pa.Check.isin(["IN", "US", "UK", "AU"])),
            "active": pa.Column(bool),
        }
    )

    def pandera_validate() -> object:
        try:
            return schema.validate(frame, lazy=True)
        except pa.errors.SchemaErrors as error:
            return error

    suite.record(
        measure(
            "pandera, lazy validation",
            group,
            pandera_validate,
            iterations=5,
            rows=size,
            notes="Vectorised checks; no contract versioning or diffing.",
        )
    )
