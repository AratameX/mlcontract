# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release states explicitly whether the **Python API** and the **contract
file format** remain compatible, because those two evolve independently: the
contract format carries its own `spec_version`.

## [Unreleased]

### Added

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

### Compatibility

- Python API: n/a (no public API yet beyond `__version__`).
- Contract format: n/a (not yet introduced).

[Unreleased]: https://github.com/AratameX/mlcontract/commits/main
