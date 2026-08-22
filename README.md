# schemapact

**Versioned data contracts that catch breaking schema changes before they reach production.**

[![CI](https://github.com/AratameX/schemapact/actions/workflows/ci.yml/badge.svg)](https://github.com/AratameX/schemapact/actions/workflows/ci.yml)
[![Docs](https://github.com/AratameX/schemapact/actions/workflows/docs.yml/badge.svg)](https://github.com/AratameX/schemapact/actions/workflows/docs.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://pypi.org/project/schemapact/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

---

## The problem

Every data pipeline depends on assumptions that live nowhere in particular.
Which columns exist. What types they are. What ranges are plausible. Which
categories are possible.

Those assumptions are real, load-bearing and invisible. When one changes — a
column renamed upstream, a dtype quietly shifting from `int64` to `object` after
a join, a new category appearing in production — nothing fails loudly. The
pipeline runs. The model returns numbers. The numbers are wrong, and you find
out from a dashboard a week later.

This is worst in machine learning, where a model will happily produce confident
predictions from data that no longer means what it did during training.

## The approach

Write the assumptions down in a form a machine can check.

```python
from schemapact import Contract, DType, Feature

contract = Contract(
    name="customer_features",
    version="1.0.0",
    features=[
        Feature("customer_id", DType.INTEGER, nullable=False, unique=True),
        Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
        Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
    ],
)

report = contract.validate(dataframe)
if not report.is_valid:
    print(report.summary())
```

```text
customer_features v1.0.0 against DataFrame (12043 rows x 3 columns)
FAILED: 2 error(s), 0 warning(s)

  ERROR   SPX203 age: Column 'age' has 3 value(s) below the declared min of 18;
          furthest is 12.
          e.g. row 41=12, row 88=15, row 203=17
          fix: Clip or filter the offending rows, or relax min if the data is
               legitimately wider than the contract assumed.
  ERROR   SPX205 country: Column 'country' has 1 value(s) outside the allowed
          set. Unexpected: FR.
```

## What makes it different

Plenty of libraries validate a dataframe. The distinguishing question here is
not "is this data valid?" but **"will this change break the people downstream?"**

A pact, not a schema: an agreement between the system producing data and the
systems consuming it, versioned like any other interface and checked in both
directions.

```bash
schemapact check-compatibility contracts/v1.yaml contracts/v2.yaml --mode backward
```

Contracts are versioned and diffable. Comparing two versions tells you what
changed, whether it is breaking, and *for whom* — because adding a required
field breaks every producer and no consumer, while removing one does the
reverse.

| Change | backward | forward |
| --- | --- | --- |
| Required field added | **breaks** | safe |
| Required field removed | safe | **breaks** |
| Constraint tightened | **breaks** | safe |
| Constraint relaxed | safe | **breaks** |

A single boolean cannot express that, which is why compatibility is always asked
in a direction.

## Installation

```bash
pip install schemapact
```

No required dependencies. Contracts are defined, validated, serialized to JSON
and diffed using the standard library alone.

| Extra | Command | Adds |
| --- | --- | --- |
| YAML | `pip install "schemapact[yaml]"` | YAML contracts |
| pandas | `pip install "schemapact[pandas]"` | DataFrame validation |
| Both | `pip install "schemapact[all]"` | |

Python 3.10+. Tested on 3.10–3.13, on Linux, macOS and Windows.

## Quickstart

Read a contract off data you already have:

```bash
schemapact init --from-csv customers.csv --output contract.yaml
schemapact validate contract.yaml customers.csv
```

Inference is deliberately cautious. Types generalise from a sample; observed
minima and maxima do not, so ranges are omitted unless you ask for them with
`--infer-ranges`. Review what it produces and tighten it where you know more
than the sample does.

## Validating

`validate()` accepts a list of dictionaries, a path to a `.csv` or `.tsv` file,
or a pandas DataFrame.

```python
report = contract.validate(data)

report.is_valid
report.errors  # violations that invalidate the data
report.warnings  # notable, but not invalidating
report.codes()  # ('SPX203', 'SPX205') — for alerting
report.for_feature("age")
report.summary()  # human-readable
report.to_json()  # machine-readable
report.raise_for_status()  # opt into fail-fast
```

**Validation returns a report rather than raising.** A real dataset usually has
several problems at once, and raising on the first turns a single CI run into a
queue of them.

Offending values make a report far more actionable, and they are raw data. Pass
`sample_values=False`, or `--no-samples` on the CLI, when reports are written
somewhere that should not hold it.

## Contracts

```yaml
spec_version: '1'          # the file format's version, owned by the library
name: customer_features    # stable across versions
version: 1.2.0             # your version, under semantic versioning

enforce_column_order: false
allow_extra_columns: true
min_rows: 1

features:
  customer_id:
    type: integer
    nullable: false
    unique: true
  country:
    type: categorical
    allowed_values: [IN, US, UK]
    description: ISO country code.
```

**Types:** `integer`, `float`, `boolean`, `string`, `categorical`, `datetime`,
`date`. Common aliases (`int64`, `str`, `category`, `timestamp`) are accepted
when reading a file.

**Constraints:** `nullable`, `required`, `min`, `max`, `allowed_values`,
`pattern`, `unique`, `max_null_fraction`. A constraint that cannot apply to a
type is rejected when the contract is built — a regex on a float is a mistake
worth hearing about immediately.

Unknown keys are rejected with a suggestion rather than ignored. Silently
dropping a misspelled `nullabe` would leave a contract that looks stricter than
it is, which is the exact failure this library exists to prevent.

## Command line

```bash
schemapact validate CONTRACT DATA
schemapact diff OLD NEW
schemapact check-compatibility OLD NEW --mode backward|forward|full
schemapact init [--from-csv PATH]
schemapact version
```

| Exit code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | The data violated the contract |
| `2` | The change is not compatible in the direction requested |
| `3` | Usage error |
| `4` | The contract itself is invalid |

`1` and `2` are deliberately distinct — "this dataset is bad" and "this schema
change breaks your consumers" call for different pipeline responses.

`--format json` is available on `validate`, `diff` and `check-compatibility`.
Errors go to standard error, so standard output stays parseable when a command
fails.

## In CI

```yaml
- run: pip install "schemapact[yaml,pandas]"

- name: Validate data
  run: schemapact validate contracts/input.yaml data/sample.csv

- name: Contract compatibility
  run: |
    git show origin/main:contracts/input.yaml > /tmp/base.yaml
    schemapact check-compatibility /tmp/base.yaml contracts/input.yaml --mode backward
```

An incompatible schema change becomes a red build instead of an incident.

## Design commitments

- **Dependency-free core.** Four of CI's ten test jobs install no extras at all
  and fail if pandas or PyYAML becomes importable. The promise is verified, not
  asserted.
- **One contract, many encodings.** JSON and YAML are encodings of a single
  representation, so the same contract in either produces an identical object.
  Property tests prove it for generated contracts, not just examples.
- **Reports, not exceptions, by default.**
- **Renames are declared, never guessed.** A compatibility tool that is
  confidently wrong is worse than one that admits it does not know.
- **Error codes are permanent.** Never reused, renumbered or repurposed, because
  people grep logs and configure alerts on them.
- **The validation engine imports no data library.** Every backend is an adapter
  behind a six-method protocol, which is why adding one is a small file rather
  than a refactor.

## Performance

Same checks, same data, same machine, 100,000 rows:

| Approach | Median | Peak memory |
| --- | ---: | ---: |
| Hand-written pandas assertions | 1.6 ms | 0.5 MB |
| **schemapact, pandas adapter** | **7.9 ms** | **0.5 MB** |
| pandera, lazy validation | 10.3 ms | 3.6 MB |

Around 13 million rows/second. Hand-written assertions are faster and always
will be — they do nothing but compute booleans, while schemapact returns
structured violations with error codes, affected-row counts, sampled values and
remediation text.

Contract operations are effectively free: a diff is 0.04 ms, a full
compatibility check 0.09 ms.

Every figure comes from `python benchmarks/run_all.py`; see
[the performance docs](docs/reference/performance.md) for methodology, caveats
and full results.

## Comparison with alternatives

| | schemapact | pandera | Great Expectations |
| --- | --- | --- | --- |
| Dataframe validation | Yes | Yes | Yes |
| Contract versioning | **Yes** | No | No |
| Breaking-change detection | **Yes** | No | No |
| Directional compatibility | **Yes** | No | No |
| Dependency-free core | **Yes** | No | No |
| Works without pandas | **Yes** | No | Partial |
| Built-in check library | Modest | Extensive | Extensive |
| Profiling and data docs | No | Partial | **Yes** |

If you need a large library of statistical checks, use pandera or Great
Expectations. If you need to know whether a schema change will break the systems
downstream, that is what this is for. They compose: nothing stops you running
pandera in the hot path and schemapact in CI.

## Documentation

- [Installation](docs/getting-started/installation.md)
- [Quickstart](docs/getting-started/quickstart.md)
- [Writing contracts](docs/guides/contracts.md)
- [Validating data](docs/guides/validation.md)
- [Breaking changes](docs/guides/compatibility.md)
- [Command line](docs/guides/cli.md)
- [Error codes](docs/reference/errors.md)
- [Architecture](docs/development/architecture.md)

## Examples

Every example in [`examples/`](examples/) is executed by CI with assertions on
its output, so none can quietly stop being true.

| Example | Shows |
| --- | --- |
| `01_quickstart.py` | Validating a list of dictionaries, no dependencies |
| `02_csv_and_inference.py` | Inferring a contract from a CSV |
| `03_breaking_changes.py` | Diffing versions and reading the direction |
| `04_pandas.py` | DataFrames, including pandas' integer-to-float promotion |
| `05_ci_gate.py` | Failing a build on an incompatible change |

## Roadmap

| Version | Scope |
| --- | --- |
| `0.1.0` | Data contracts: schema, constraints, reports, JSON/YAML, diff, compatibility, pandas, CLI |
| `0.2.0` | Model contracts, prediction validation, metric thresholds, scikit-learn |
| `0.3.0` | Polars, PyTorch, XGBoost, custom validator hooks |
| `1.0.0` | Stable contract format and Python API |

## Versioning and stability

This project follows [Semantic Versioning](https://semver.org). Before `1.0.0`,
minor versions may contain breaking API changes; each is described in
[CHANGELOG.md](CHANGELOG.md).

Two versions evolve independently:

- The **Python API**, versioned by releases of this package.
- The **contract file format**, carried in each contract's `spec_version`. A
  release that cannot read an older format is a breaking change and will say so.

`schemapact.__all__` is the compatibility promise. Anything not listed there is
internal and may change without notice, and a test fails if a public symbol
disappears without the snapshot being updated in the same commit.

## Contributing

```bash
git clone https://github.com/AratameX/schemapact
cd schemapact
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
python scripts/check.py
```

`scripts/check.py` runs the same lint, type and test sequence CI does, so a green
run locally means a green build. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Support

- **Bugs and feature requests:** [GitHub Issues](https://github.com/AratameX/schemapact/issues)
- **Security:** see [SECURITY.md](SECURITY.md) — please do not open a public issue

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
