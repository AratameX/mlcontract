# Quickstart

## 1. Get a contract

The fastest start is to read one off data you already have:

```bash
mlcontract init --from-csv customers.csv --output contract.yaml
```

```yaml
spec_version: '1'
name: customers
version: 0.1.0
description: Inferred from customers.csv. Review before relying on it.
features:
  customer_id:
    type: integer
    nullable: false
  age:
    type: integer
  country:
    type: categorical
    allowed_values: [IN, UK, US]
```

Review it. Inference is deliberately cautious: types generalise from a sample,
but observed minima and maxima do not, so ranges are left out unless you pass
`--infer-ranges`. Tighten it by hand where you know more than the sample does.

## 2. Validate

```bash
mlcontract validate contract.yaml customers.csv
```

```
customers v0.1.0 against customers.csv (1204 rows)
FAILED: 1 error(s), 0 warning(s)

  ERROR   MLC203 age: Column 'age' has 3 value(s) below the declared min of 18;
          furthest is 12.
          e.g. row 41=12, row 88=15, row 203=17
          fix: Clip or filter the offending rows, or relax min if the data is
               legitimately wider than the contract assumed.
```

Or from Python:

```python
from mlcontract import Contract

contract = Contract.load("contract.yaml")
report = contract.validate(dataframe)

if not report.is_valid:
    print(report.summary())
```

Validation returns a report rather than raising, because a real dataset usually
has several problems at once and you want all of them from one run. Call
`report.raise_for_status()` if you would rather fail fast.

## 3. Guard the contract itself

Commit the contract, then check every proposed change against it:

```bash
mlcontract check-compatibility contracts/v1.yaml contracts/v2.yaml --mode backward
```

Exit code 2 means the change breaks existing data. Wire that into CI and an
incompatible schema change fails the build instead of reaching production.

## Next

- [Writing contracts](../guides/contracts.md) — every constraint available
- [Breaking changes](../guides/compatibility.md) — what backward, forward and full mean
