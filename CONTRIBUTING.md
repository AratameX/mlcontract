# Contributing

Thanks for considering it. This document covers the mechanics; if anything here
is unclear or wrong, that is itself worth an issue.


## Setup

```bash
git clone https://github.com/AratameX/mlcontract
cd mlcontract
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## The gate

```bash
python scripts/check.py          # lint, format, types, tests
python scripts/check.py --fix    # apply what can be fixed automatically
```

This runs the same sequence as CI, in the same order, so green here means green
there. Pre-commit hooks use the tools from your virtual environment rather than
separately pinned versions, so local checks and CI can never disagree about
which ruff or mypy is authoritative.

## What CI enforces

- ruff lint and format
- mypy in strict mode
- 90% branch coverage minimum
- Tests on Python 3.10–3.13, in two dependency shapes: **core** (no extras) and
  **full**
- Tests on Linux, macOS and Windows
- Every example in `examples/` runs and produces the output it claims
- The generated error-code reference matches the registry
- The public API snapshot matches `mlcontract.__all__`

The core-only jobs matter most. They fail if an optional dependency leaks into
the core, which is the promise most easily broken by accident.

## Conventions

**Tests are written against the public API** wherever possible, so they survive
refactoring and fail when behaviour users depend on changes.

**Every fixed bug gets a test** that fails without the fix, named for what it
protects rather than the issue number.

**Comments explain why, not what.** If a line needs explaining, the explanation
is usually about a trade-off or a trap, not about the syntax.

**Changing the public API** requires updating `EXPECTED_PUBLIC_API` in
`tests/compatibility/test_public_api.py` in the same pull request. That is the
point: the update is the review signal.

**Error codes are permanent.** Add new ones; never renumber existing ones. Run
`python scripts/generate_error_docs.py` after adding one.

## Commits and pull requests

Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.

Describe *why* in the pull request body. What changed is visible in the diff;
why it changed is not.

## Design decisions worth knowing before you change them

Several things in this codebase look like they could be simplified and cannot.
Each has a comment explaining why, but the recurring ones:

- **Constraint "is this set?" checks compare by identity, not equality.**
  `value in (None, False)` is wrong because `0 == False` in Python, which
  silently discards `min=0`. This shipped once and was caught by property tests.
- **Forward compatibility is not implemented separately.** It is backward
  compatibility with the arguments swapped. Implementing it directly would let
  the two directions drift apart.
- **`ValidationReport` deliberately has no `__bool__`.** It would have to mean
  either "is valid" or "has violations", and those are opposites.
- **Vectorised adapter methods may return `None`.** That means "I decline this
  case", and the engine falls back to iteration. Correctness never depends on a
  fast path.

## Reporting bugs

A reproducing case beats a description. The smallest contract and dataset that
demonstrate the problem, plus what you expected, is enough — include the error
code if there is one.
