# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release states explicitly whether the **Python API** and the **contract
file format** remain compatible, because those two evolve independently: the
contract format carries its own `spec_version`.

## [Unreleased]

Nothing yet.

## [0.1.1] - 2026-08-22

### Fixed

- Every link on the PyPI project page was a 404. The README used relative
  links, which GitHub resolves against the repository and PyPI resolves against
  `pypi.org/project/schemapact/`, where no such files exist. All fifteen are now
  absolute URLs, which work identically in both places.

### Compatibility

- Python API: unchanged.
- Contract format: unchanged, `spec_version` 1.

## [0.1.0] - 2026-08-22

First release. Data contracts: define the shape a dataset must have, validate
real data against it, and compare contract versions to find out whether a change
breaks the systems downstream.

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
- Structural checks (`SPX101`-`SPX106`): missing required columns, undeclared
  columns, column order, column types, row-count bounds.
- Value checks (`SPX201`-`SPX208`): nullability, null fraction, ranges, allowed
  values, patterns, uniqueness.
- Validation exception family, raised only via `raise_for_status()`.
- `sample_values=False` for reports written where raw data should not go.

- pandas adapter, behind the `pandas` extra and imported lazily, so the core
  install never pulls pandas in. Explicit dtype mapping covering NumPy and
  nullable extension types, categoricals, timezone-aware datetimes, and dates
  held in object columns.
- pandas' four spellings of missing — `NaN`, `None`, `NaT` and `pd.NA` — are all
  handled by delegating to `isna` rather than reimplementing the rules.

- Contract diffing. `old.diff(new)` returns every difference, each classified
  by whether it admits more data (`RELAXED`), less (`TIGHTENED`), or neither
  (`NEUTRAL`). Tightened is exactly what "breaking" means.
- Directional compatibility. `old.is_compatible_with(new, mode)` answers
  `backward` (can the new contract read old data?), `forward` (can the old
  contract read new data?), or `full`. A single boolean cannot express this:
  adding a required field breaks producers and not consumers.
- Implied semantic-version bumps. `diff.required_bump` is derived from the
  changes, and `is_version_bump_sufficient` catches a breaking change shipped
  as a patch release — the check worth putting in CI.
- Declared renames via `previous_names` are reported once as a rename rather
  than as an unrelated removal and addition. Renames are never inferred.
- Compatibility error codes `SPX601` and `SPX602`, and `CompatibilityError`.

- Command-line interface: `schemapact validate`, `diff`, `check-compatibility`,
  `init` and `version`, with `--format text|json` throughout.
- Documented exit codes, treated as part of the public interface: 0 success,
  1 data violated the contract, 2 incompatible change, 3 usage error, 4 invalid
  contract. 1 and 2 are deliberately distinct — "this dataset is bad" and "this
  schema change breaks your consumers" call for different pipeline responses.
- `schemapact init --from-csv` infers a starting contract from existing data.
  Types generalise, so they are inferred; observed minima and maxima do not, so
  ranges are opt-in behind `--infer-ranges`.
- `--no-samples` on validate, for reports written where raw values should not go.
- Errors are written to stderr, so `--format json` on stdout stays parseable
  even when a command fails.

- Documentation site built with MkDocs Material and mkdocstrings, so the API
  reference is generated from the docstrings and cannot drift from the code.
- Five runnable examples in `examples/`, each executed by CI with assertions on
  their output. An example that is never run stops being documentation and
  becomes a claim nobody checks.
- `scripts/generate_error_docs.py` renders the error-code reference from the
  registry; CI fails if the committed page is stale.
- `docs.yml` workflow: builds with `--strict`, so a broken internal link fails
  the build.
- CI now runs on macOS and Windows as well as Linux. The full Python matrix
  stays on Linux; the other two get one version each, because the bugs they
  catch are about paths, encodings and line endings rather than language
  versions.

- Benchmark suite in `benchmarks/`, recording contract operations, validation
  throughput and an honest comparison against hand-written pandas assertions and
  pandera. Every result embeds the environment that produced it.
- `performance.yml` workflow: weekly full runs with archived results, plus a
  fast smoke job so a refactor cannot silently break the measurement code.
- Performance documentation and a README section, both populated from the
  recorded results rather than written by hand.

- Optional `VectorisedSource` protocol. A backend may implement per-check
  methods that evaluate a whole column at once; the engine falls back to
  iteration for any it does not provide, so correctness never depends on a fast
  path existing.
- The pandas adapter implements all five, making validation **12× faster and 6×
  lighter** — 154 ms to 12.8 ms on 100,000 rows, and 3.1 MB to 0.5 MB — with no
  change to the engine and no change to what any report says. schemapact now
  measures faster than pandera on the same benchmark.
- Equivalence tests running identical data through both paths and comparing
  entire reports, because a fast path that quietly disagrees with the slow one
  is worse than no fast path at all.

### Fixed

- Row numbers reported by the pandas adapter closed up behind nulls: values were
  filtered before being enumerated, so every reported row after the first null
  pointed at the wrong record. Found by the fast-path equivalence tests, which
  disagreed with each other. A Phase 3 test had encoded the wrong behaviour as
  expected.
- Value checks no longer accumulate every offending row in memory to display a
  handful of samples. Counting without collecting keeps memory flat regardless
  of how broken the data is — worst exactly when the dataset is largest.

- Vectorised fast paths in the pandas adapter for range, allowed-value, pattern
  and uniqueness checks. Validating 100,000 rows went from 154 ms to 13 ms — an
  11× improvement, with the validation engine unchanged, which is what the
  adapter protocol existed for. schemapact is now faster than pandera on the
  same workload.
- Equivalence tests running identical data through the fast and slow paths and
  asserting the reports match exactly. Two implementations of one check is the
  arrangement most likely to drift.

- Full README covering the problem, the differentiator, installation, contracts,
  validation, the CLI, CI usage, performance, an honest comparison against
  pandera and Great Expectations, versioning policy and support.
- `SECURITY.md` with a private reporting channel and a real threat model —
  contracts are untrusted input, regular expressions in them are not sandboxed,
  and reports may carry sampled data.
- `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, issue forms and a pull-request
  template.
- Dependabot for GitHub Actions and pip, with development tooling grouped so a
  week of individual bumps is one pull request.
- `pip-audit` in CI against the full dependency tree, failing the build on a
  known vulnerability.
- Tests keeping the community files honest: no surviving placeholders, README
  links resolve, the security policy offers a private channel, and the declared
  licence matches the package metadata.

- Release workflow using PyPI Trusted Publishing: no API token exists anywhere
  in the repository or its secrets. Every tagged release builds, publishes to
  TestPyPI, installs from TestPyPI and runs a smoke test, and only then waits
  for manual approval before touching PyPI.
- The workflow refuses to publish when the tag and the package version disagree,
  because publishing the wrong artifact under the right name cannot be undone.
- Release runbook in `docs/development/releasing.md`, including one-time
  Trusted Publishing setup and what to do when a release goes wrong.
- Release-readiness tests: version wiring, console-script target importability,
  advertised Python versions matching the floor, and the publish workflow's own
  ordering and permissions.

### Changed

- A pandas float column that contains nulls and holds only whole numbers is
  read as `integer`. pandas promotes integer columns to `float64` the moment a
  null appears, and treating that storage artifact as a type violation would
  fail contracts for reasons unrelated to their data. Narrowly scoped: a float
  column *without* nulls is taken at face value, so genuine float data is never
  quietly accepted where an integer was required.
- `mkdocs` is pinned below 2.0: that release removes the plugin and theming
  systems with no migration path.
- CSV and contract files are read as `utf-8-sig` rather than `utf-8`, so a
  byte-order mark is stripped instead of absorbed. Windows tools — Excel,
  Notepad, PowerShell's `Out-File` — write UTF-8 with a BOM by default, and
  without this the mark became part of the first column's name, producing a
  header like `"\ufeffid"` that silently matched nothing. Found by running the
  CLI by hand on Windows; no Linux test could have caught it.
- `schemapact.cli.__init__` no longer re-exports the `main` function. Binding it
  there shadowed the `main` submodule of the same name, so even
  `import schemapact.cli.main` returned the function.
- `ValidationReport` deliberately defines no `__bool__`. It would have to mean
  either "is valid" or "has violations" — opposites — while `__len__` already
  implies the second. Callers say `report.is_valid`.


- Project bootstrap: `src/` layout, canonical `pyproject.toml`, Apache-2.0
  license, dependency-free core.
- Tooling baseline: ruff (lint + format), mypy in strict mode, pytest with
  branch coverage gated at 90%.
- Public API snapshot test guarding `schemapact.__all__` against accidental
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
- Exception hierarchy (`SchemaPactError`, `ContractDefinitionError`,
  `IntegrationError`) and a permanent error-code registry, `SPX001`–`SPX014`
  and `SPX901`.
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

[Unreleased]: https://github.com/AratameX/schemapact/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/AratameX/schemapact/releases/tag/v0.1.1
[0.1.0]: https://github.com/AratameX/schemapact/releases/tag/v0.1.0
