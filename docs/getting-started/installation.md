# Installation

```bash
pip install mlcontract
```

That is the whole core. It has **no required dependencies** — contracts are
defined, validated, serialized to JSON and diffed using the standard library
alone.

## Extras

Install these only if you need them.

| Extra | Command | Adds |
| --- | --- | --- |
| YAML | `pip install "mlcontract[yaml]"` | Reading and writing YAML contracts |
| pandas | `pip install "mlcontract[pandas]"` | Validating DataFrames |
| Both | `pip install "mlcontract[all]"` | |

Using a feature whose extra is missing produces an error naming the exact
command to run, rather than an `ImportError` from somewhere unrelated:

```
IntegrationError [MLC901]: Reading and writing YAML contracts requires the
optional 'yaml' extra, which provides 'PyYAML'. Install it with:

    pip install "mlcontract[yaml]"
```

## Requirements

Python 3.10 or newer. Tested on 3.10, 3.11, 3.12 and 3.13, on Linux, macOS and
Windows.

## Verify

```bash
mlcontract version
```

## Development install

```bash
git clone https://github.com/AratameX/mlcontract
cd mlcontract
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
python scripts/check.py
```

`scripts/check.py` runs the same lint, type and test sequence CI does, so a
green run locally means a green build.
