# mlcontract

**Executable contracts for ML systems — validate data, models and predictions before they break production.**

## The problem

Every ML system depends on assumptions that live nowhere in particular. Which
columns the model expects. What types they are. What ranges are plausible. Which
categories exist. What the output looks like.

Those assumptions are real, load-bearing and invisible. When one changes — a
column renamed upstream, a dtype quietly shifting from `int64` to `object` after
a join, a new category appearing in production — nothing fails loudly. The
pipeline runs. The model returns numbers. The numbers are wrong, and you find
out from a dashboard a week later.

## The approach

Write the assumptions down in a form a machine can check.

```python
from mlcontract import Contract, DType, Feature

contract = Contract(
    name="customer_features",
    version="1.0.0",
    features=[
        Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
        Feature("country", DType.CATEGORICAL, allowed_values=["IN", "US", "UK"]),
    ],
)

report = contract.validate(dataframe)
if not report.is_valid:
    print(report.summary())
```

## What makes it different

Plenty of libraries validate a dataframe. The distinguishing question here is
not "is this data valid?" but **"will this change break the people downstream?"**

```bash
mlcontract check-compatibility contracts/v1.yaml contracts/v2.yaml --mode backward
```

Contracts are versioned and diffable. Comparing two versions tells you what
changed, whether it is breaking, and *for whom* — because adding a required
field breaks every producer and no consumer, while removing one does the
reverse. That check belongs in CI, where an incompatible schema change becomes a
red build instead of an incident.

## Design commitments

- **Dependency-free core.** Defining, validating, serializing and diffing
  contracts uses the standard library alone. pandas, YAML and ML frameworks are
  optional extras, and CI verifies the core install really has none.
- **One contract, many encodings.** JSON and YAML are encodings of a single
  representation, so the same contract in either produces an identical object.
- **Reports, not exceptions, by default.** Real datasets have several problems
  at once. You get all of them from one run.
- **Renames are declared, never guessed.** A compatibility tool that is
  confidently wrong is worse than one that admits it does not know.

## Where to go next

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md) — a working contract in five minutes
- [Breaking changes](guides/compatibility.md) — the part worth reading twice
