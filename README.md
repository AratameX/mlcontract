# mlcontract

**Executable contracts for ML systems — validate data, models and predictions before they break production.**

> **Status: pre-alpha, under active development.** The API may change before
> `v0.1.0`, when this notice is removed.

---

## The problem

Every ML system depends on assumptions that live nowhere in particular: which
columns the model expects, what types they are, what ranges are plausible, which
categories exist, what the output looks like, which model version the serving
layer was built against.

Those assumptions are real, load-bearing, and invisible. When one changes — a
column gets renamed upstream, a dtype silently shifts from `int64` to `object`, a
new category appears in production — nothing fails loudly. The pipeline runs. The
model returns numbers. The numbers are wrong, and you find out from a dashboard a
week later.

## The approach

`mlcontract` turns those assumptions into a versioned, machine-readable contract
you can validate against real data, compare across versions, and enforce in CI.

```python
from mlcontract import Contract

contract = Contract.from_yaml("customer_features.yaml")
report = contract.validate(df)

if not report.is_valid:
    print(report.summary())
```

And in CI, the check that matters most:

```bash
mlcontract check-compatibility contracts/v1.yaml contracts/v2.yaml --mode backward
```

A breaking change becomes a failed build instead of a production incident.

## Design commitments

- **Dependency-free core.** Defining, validating, serializing and diffing contracts
  uses the standard library only. pandas, YAML and every ML framework are extras.
- **One contract, many encodings.** JSON and YAML are encoders over a single
  canonical representation. The same contract in either format produces an
  identical `Contract` object — there is no second parsing path to drift.
- **Reports, not exceptions, by default.** Real datasets have many problems at
  once. You get all of them in one run; `raise_for_status()` is there when you
  want fail-fast instead.
- **Directional compatibility.** "Is this breaking?" depends on whether you are
  the producer or the consumer. Compatibility is checked as `backward`, `forward`
  or `full`, not as a single boolean.
- **Renames are declared, never guessed.** A compatibility tool that is
  confidently wrong is worse than one that admits it does not know.

## Performance

Same checks, same data, same machine, 100,000 rows:

| Approach | Median | Peak memory |
| --- | ---: | ---: |
| Hand-written pandas assertions | 3.0 ms | 0.5 MB |
| **mlcontract, pandas adapter** | **12.8 ms** | **0.5 MB** |
| pandera, lazy validation | 15.8 ms | 3.6 MB |

Around 7.8 million rows/second. Hand-written assertions are faster and always
will be — they do nothing but compute booleans, while mlcontract returns
structured violations with error codes, affected-row counts, sampled values and
remediation text.

Contract operations are effectively free: a diff is 0.05 ms, a full
compatibility check 0.11 ms.

Every figure comes from `python benchmarks/run_all.py`; see
[docs/reference/performance.md](docs/reference/performance.md) for methodology
and the full results.

## Roadmap

| Version | Scope |
|---|---|
| `0.1.0` | Data contracts: schema, constraints, validation reports, JSON/YAML, diff, compatibility, pandas adapter, CLI |
| `0.2.0` | Model contracts, prediction validation, metric thresholds, scikit-learn |
| `0.3.0` | PyTorch, XGBoost, Polars, custom validator hooks |
| `1.0.0` | Stable contract format and Python API |

## Development

```bash
git clone https://github.com/AratameX/mlcontract
cd mlcontract
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check . && ruff format --check .
mypy
pytest
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
