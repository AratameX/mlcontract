"""Timing harness and environment capture.

A benchmark number without its environment is not a measurement, it is an
anecdote. Every result records the library version, Python version, operating
system, CPU and dependency versions alongside it, so a figure from six months
ago can still be interpreted — and so a "regression" can be recognised as a
runner change rather than a code change.

Statistics are reported as median and p95 rather than mean. A mean over a
handful of runs is dominated by whatever else the machine was doing; the median
is what a user actually experiences, and p95 is what they complain about.
"""

from __future__ import annotations

import gc
import json
import platform
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass(frozen=True, slots=True)
class Measurement:
    """One benchmark's timings.

    Attributes:
        name: What was measured.
        group: Which benchmark file it came from.
        rows: Dataset size, where the notion applies.
        iterations: How many times it ran.
        median_ms: Median wall time in milliseconds.
        p95_ms: 95th-percentile wall time.
        min_ms: Fastest observed run, the closest thing to a floor.
        rows_per_second: Throughput, where rows apply.
        peak_memory_mb: Peak Python allocation during one run.
        notes: Anything a reader needs to interpret the number.
    """

    name: str
    group: str
    iterations: int
    median_ms: float
    p95_ms: float
    min_ms: float
    rows: int | None = None
    rows_per_second: float | None = None
    peak_memory_mb: float | None = None
    notes: str | None = None


@dataclass
class Suite:
    """A collection of measurements plus the environment that produced them."""

    measurements: list[Measurement] = field(default_factory=list)

    def record(self, measurement: Measurement) -> None:
        """Add a measurement and print it as it completes."""
        self.measurements.append(measurement)
        print(f"  {_format(measurement)}")

    def to_dict(self) -> dict[str, Any]:
        """Return the full record, environment included."""
        return {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "environment": environment(),
            "measurements": [asdict(m) for m in self.measurements],
        }

    def save(self, directory: Path | None = None) -> Path:
        """Write the results as timestamped JSON."""
        target = directory or RESULTS_DIR
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = target / f"{stamp}.json"
        # newline="\n" rather than the platform default. .gitattributes mandates
        # LF, so writing CRLF on Windows would make the pre-commit hook rewrite
        # every results file and abort the commit.
        path.write_text(
            json.dumps(self.to_dict(), indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return path


def environment() -> dict[str, Any]:
    """Capture everything needed to interpret a number later."""
    import mlcontract

    return {
        "mlcontract": mlcontract.__version__,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "dependencies": _dependency_versions(),
    }


def measure(
    name: str,
    group: str,
    operation: Callable[[], object],
    *,
    iterations: int = 20,
    warmup: int = 3,
    rows: int | None = None,
    notes: str | None = None,
) -> Measurement:
    """Time an operation and return its statistics.

    Args:
        name: What is being measured.
        group: The benchmark file this belongs to.
        operation: A zero-argument callable, timed as a whole.
        iterations: How many timed runs.
        warmup: Untimed runs first. Imports, caches and branch predictors all
            warm up, and including that cost measures the first call rather than
            the steady state.
        rows: Dataset size, for throughput.
        notes: Context a reader needs.

    Returns:
        The measurement.
    """
    for _ in range(warmup):
        operation()

    # Garbage collection is disabled during timing so a collection triggered by
    # unrelated allocation cannot land inside one iteration and skew it.
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()

    timings: list[float] = []
    try:
        for _ in range(iterations):
            started = time.perf_counter()
            operation()
            timings.append((time.perf_counter() - started) * 1000)
    finally:
        if was_enabled:
            gc.enable()

    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    median = statistics.median(timings)
    return Measurement(
        name=name,
        group=group,
        rows=rows,
        iterations=iterations,
        median_ms=round(median, 4),
        p95_ms=round(_percentile(timings, 95), 4),
        min_ms=round(min(timings), 4),
        rows_per_second=round(rows / (median / 1000)) if rows and median else None,
        peak_memory_mb=round(peak / 1_048_576, 3),
        notes=notes,
    )


def _percentile(values: list[float], percentile: float) -> float:
    """Return a percentile by nearest rank."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(percentile / 100 * len(ordered) + 0.5) - 1)
    return ordered[index]


def _dependency_versions() -> dict[str, str]:
    """Record versions of the optional packages that affect timings."""
    import importlib.metadata as metadata

    found: dict[str, str] = {}
    for package in ("pandas", "numpy", "PyYAML", "pandera"):
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = "not installed"
    return found


def _format(measurement: Measurement) -> str:
    """Render one measurement as a single readable line."""
    parts = [f"{measurement.name:<48}", f"{measurement.median_ms:>9.3f} ms"]
    if measurement.rows_per_second:
        parts.append(f"{measurement.rows_per_second:>12,} rows/s")
    if measurement.peak_memory_mb:
        parts.append(f"{measurement.peak_memory_mb:>7.1f} MB")
    return "  ".join(parts)


def announce(title: str) -> None:
    """Print a section heading."""
    print(f"\n{title}\n{'-' * len(title)}", file=sys.stdout)
