"""Run every benchmark and record the results.

    python benchmarks/run_all.py              # run and save
    python benchmarks/run_all.py --quick      # smaller sizes, for a smoke test
    python benchmarks/run_all.py --no-save    # print only

Results are written to ``benchmarks/results/`` as timestamped JSON, with the
environment embedded. Committing them gives later runs something to compare
against, and gives the README numbers a provenance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks import bench_comparison, bench_contract, bench_validation
from benchmarks._harness import Suite, environment


def main(argv: list[str] | None = None) -> int:
    """Run the suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="use smaller datasets")
    parser.add_argument("--no-save", action="store_true", help="print without writing")
    args = parser.parse_args(argv)

    if args.quick:
        bench_validation.SIZES = (100, 1_000)

    print("schemapact benchmarks")
    print(json.dumps(environment(), indent=2))

    suite = Suite()
    bench_contract.run(suite)
    bench_contract.run_diff(suite)
    bench_validation.run(suite)
    if not args.quick:
        bench_comparison.run(suite)

    print(f"\n{len(suite.measurements)} measurements.")

    if not args.no_save:
        path = suite.save()
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
