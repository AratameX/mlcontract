"""Run the full local quality gate.

This is the same sequence CI runs, in the same order, so a green run here means
a green run there. It exists so the gate is a single command in any editor:
PyCharm, VS Code, or a bare terminal.

    python scripts/check.py            # lint, format, types, tests
    python scripts/check.py --fix      # auto-fix what can be fixed, then check
    python scripts/check.py --fast     # skip coverage for a quicker loop

Exit code is 0 only if every step passed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _supports_colour() -> bool:
    return sys.stdout.isatty()


def _paint(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if _supports_colour() else text


def run_step(name: str, command: list[str]) -> bool:
    """Run one step, printing its outcome. Returns True if it passed."""
    print(f"\n{_paint('▶', BOLD)} {_paint(name, BOLD)}")
    print(_paint(f"  $ {' '.join(command)}", DIM))

    started = time.perf_counter()
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    elapsed = time.perf_counter() - started

    if result.returncode == 0:
        print(_paint(f"  ✓ {name} passed ({elapsed:.1f}s)", GREEN))
        return True

    print(_paint(f"  ✗ {name} failed ({elapsed:.1f}s)", RED))
    return False


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="apply Ruff's automatic fixes and formatting before checking",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="skip coverage measurement for a quicker feedback loop",
    )
    args = parser.parse_args()

    for tool in ("ruff", "mypy", "pytest"):
        if shutil.which(tool) is None:
            print(
                _paint(f"✗ {tool} not found on PATH.", RED),
                'Activate your virtual environment and run:  pip install -e ".[dev]"',
                sep="\n  ",
            )
            return 1

    if args.fix:
        run_step("Ruff auto-fix", ["ruff", "check", "--fix", "."])
        run_step("Ruff format", ["ruff", "format", "."])

    pytest_command = ["pytest", "-q"]
    if not args.fast:
        pytest_command += [
            "--cov=schemapact",
            "--cov-branch",
            "--cov-report=term-missing",
        ]

    steps: list[tuple[str, list[str]]] = [
        ("Lint (ruff check)", ["ruff", "check", "."]),
        ("Format (ruff format --check)", ["ruff", "format", "--check", "."]),
        ("Types (mypy --strict)", ["mypy"]),
        ("Tests (pytest)", pytest_command),
    ]

    failed = [name for name, command in steps if not run_step(name, command)]

    print()
    if failed:
        print(_paint(f"{len(failed)} step(s) failed: {', '.join(failed)}", RED + BOLD))
        if not args.fix:
            print(_paint("  Tip: many lint and format failures fix themselves with", DIM))
            print(_paint("       python scripts/check.py --fix", DIM))
        return 1

    print(_paint("All checks passed.", GREEN + BOLD))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
