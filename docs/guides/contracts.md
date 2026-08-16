# Writing contracts

A contract describes the data a component expects. It is immutable and validated
at construction, so a contract that exists is a valid one — mistakes surface
where you wrote them, not deep inside a run against a million rows.

## Anatomy

```yaml
spec_version: '1'          # the file format's version, owned by the library
name: customer_features    # stable across versions
version: 1.2.0             # your version, under semantic versioning
description: Inputs to the churn model.

enforce_column_order: false
allow_extra_columns: true
min_rows: 1
max_rows: 10000000

features:
  customer_id:
    type: integer
    nullable: false
    unique: true

metadata:
  owner: ml-platform
```

`spec_version` and `version` are deliberately separate. Yours changes when your
data changes; the format's changes only when the library's file format does.
Without that split, the format could never evolve without invalidating every
contract already committed to a repository.

## Types

| Type | Accepts |
| --- | --- |
| `integer` | Whole numbers. Not booleans — those are their own type. |
| `float` | Real numbers. Integers satisfy a float contract, since every integer is a valid float. |
| `boolean` | True or false. |
| `string` | Any text. |
| `categorical` | Text from a known domain. Pair with `allowed_values`. |
| `datetime` | A point in time, with or without a timezone. |
| `date` | A calendar date. |

Common aliases are accepted when reading a contract file: `int`, `int64`, `str`,
`bool`, `category`, `timestamp` and others.

`object` is **not** an alias for `string`. In pandas it means "anything at all",
so reading it as text would make the contract claim something the data does not
support.

## Constraints

| Constraint | Applies to | Meaning |
| --- | --- | --- |
| `nullable` | all | Whether nulls are permitted. Default `true`. |
| `required` | all | Whether the column must be present. Default `true`. |
| `min` / `max` | numeric | Inclusive bounds. |
| `allowed_values` | discrete | The complete permitted domain. |
| `pattern` | text | A regular expression every value must match. |
| `unique` | all | Whether duplicates are rejected. |
| `max_null_fraction` | all | Largest permitted proportion of nulls, 0 to 1. |

Constraints that cannot apply are rejected when the contract is built, not
ignored — a regex on a float is a mistake worth hearing about immediately.

## Required versus nullable

Two different questions, frequently conflated:

- **`required`** — must the *column* be there?
- **`nullable`** — may individual *values* be missing?

A required, non-nullable feature must be present and fully populated. An
optional, nullable one may be absent entirely, and may be full of nulls when
present.

## Renames

Declare them. They are never inferred.

```yaml
features:
  customer_age:
    type: integer
    previous_names: [age]
```

Guessing that `age` became `customer_age` produces a confident answer that is
sometimes wrong, and a compatibility tool that is confidently wrong is worse
than one that admits it does not know. Declared renames are reported as renames;
undeclared ones as a removal and an addition.

## Formats

JSON and YAML are encodings of one representation. The same contract in either
produces an identical object, and `Contract.load()` picks the format from the
file extension.

```python
contract.save("contract.yaml")
contract.save("contract.json")
Contract.load("contract.yaml") == Contract.load("contract.json")  # True
```

JSON works in a bare install. YAML needs `pip install "mlcontract[yaml]"`.

## Unknown keys are rejected

```yaml
features:
  age:
    type: integer
    nullabe: false   # typo
```

```
ContractDefinitionError [MLC002]: Unrecognised key 'nullabe' in feature 'age'.
Did you mean 'nullable'?
```

Silently ignoring it would leave a contract that looks stricter than it is,
which is the exact failure this library exists to prevent.
