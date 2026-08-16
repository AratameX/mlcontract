# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release states explicitly whether the **Python API** and the **contract
file format** remain compatible, because those two evolve independently: the
contract format carries its own `spec_version`.

## [Unreleased]

### Added

- Validation engine. `Contract.validate(data)` and the module-level
  `validate(contract, data)` check real data and return a `ValidationReport`.
- `DataSource` protocol: the engine imports no data library at all, so any
  backend can be added by implementing six methods.
- Stdlib adapters for `list[dict]` and CSV/TSV files. CSV carries no types, so
  the contract supplies them; a field that will not parse keeps its original
  text rather than being silently coerced to null.
- `ValidationReport`, `Violation`, `Sample` and `Severity`. Reports carry error
  codes, affected row counts, sampled offending values with row positions, and
  remediation text, and render as text or JSON.
- Structural checks (`MLC101`-`MLC106`): missing required columns, undeclared
  columns, column order, column types, row-count bounds.
- Value checks (`MLC201`-`MLC208`): nullability, null fraction, ranges, allowed
  values, patterns, uniqueness.
- Validation exception family, raised only via `raise_for_status()`.
- `sample_values=False` for reports written where raw data should not go.

- pandas adapter, behind the `pandas` extra and imported lazily, so the core
  install never pulls pandas in. Explicit dtype mapping covering NumPy and
  nullable extension types, categoricals, timezone-aware datetimes, and dates
  held in object columns.
- pandas' four spellings of missing — `NaN`, `None`, `NaT` and `pd.NA` — are all
  handled by delegating to `isna` rather than reimplementing the rules.

### Changed

- A pandas float column that contains nulls and holds only whole numbers is
  read as `integer`. pandas promotes integer columns to `float64` the moment a
  null appears, and treating that storage artifact as a type violation would
  fail contracts for reasons unrelated to their data. Narrowly scoped: a float
  column *without* nulls is taken at face value, so genuine float data is never
  quietly accepted where an integer was required.
- `ValidationReport` deliberately defines no `__bool__`. It would have to mean
  either "is valid" or "has violations" — opposites — while `__len__` already
  implies the second. Callers say `report.is_valid`.


- Project bootstrap: `src/` layout, canonical `pyproject.toml`, Apache-2.0
  license, dependency-free core.
- Tooling baseline: ruff (lint + format), mypy in strict mode, pytest with
  branch coverage gated at 90%.
- Public API snapshot test guarding `mlcontract.__all__` against accidental
  removals.
- Continuous integration running lint, type checks, tests, package build and a
  clean-environment import smoke test.
- `scripts/check.py`, an editor-independent runner for the full local quality
  gate in the same order CI runs it.
- Pre-commit hooks wired to the virtual environment's own tools, so local hooks
  and CI can never disagree about tool versions.
- Shared editor configuration for VS Code contributors (`.vscode/`).
- `.gitattributes` enforcing LF line endings in both index and working tree, so
  Windows checkouts do not conflict with the `mixed-line-ending` hook.

- Core domain model: `Contract` and `Feature`, immutable and validated at
  construction, so an object that exists is a valid contract.
- Canonical type system (`DType`) with common aliases and an explicit widening
  relation, which later underpins breaking-change detection.
- Declarative constraint catalogue: `min`, `max`, `allowed_values`, `pattern`,
  `unique`, `max_null_fraction`, each declaring the types it applies to and the
  direction in which it relaxes.
- Contract-level rules: required and optional features, column ordering, extra
  columns, and row-count bounds.
- Serialisation to and from JSON and YAML through one canonical dictionary
  representation, so both formats produce identical objects.
- `spec_version` on every contract, separate from the author's own `version`,
  so the file format can evolve without invalidating stored contracts.
- Exception hierarchy (`MLContractError`, `ContractDefinitionError`,
  `IntegrationError`) and a permanent error-code registry, `MLC001`–`MLC014`
  and `MLC901`.
- Unknown keys in contract documents are rejected with a suggested correction
  rather than silently ignored.
- Declared feature renames via `previous_names`. Renames are never inferred.
- Property-based tests covering round-trip losslessness, JSON/YAML equivalence
  and serialisation determinism.

- CI now runs the test matrix in two dependency shapes, core-only and full, so
  the dependency-free core is verified rather than assumed.

### Fixed

- Zero-valued constraints (`min=0`, `max=0`, `max_null_fraction=0.0`) were
  treated as undeclared, because `0 == False` in Python made the containment
  test `value in (None, False)` true. They were dropped from serialised
  contracts and skipped during applicability checking. Found by the property
  tests before any release.
- Optional-dependency tests were skipped a whole module at a time, which
  silently dropped the JSON serialisation tests in environments without PyYAML
  even though they need no YAML. Skipping is now per-test.

### Compatibility

- Python API: first public surface. `Contract`, `Feature`, `DType`,
  `SPEC_VERSION`, and the three exception types.
- Contract format: `spec_version` 1, introduced here.

[Unreleased]: https://github.com/AratameX/mlcontract/commits/main
