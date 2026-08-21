# Validating data

```python
report = contract.validate(data)
```

`data` may be a list of dictionaries, a path to a `.csv` or `.tsv` file, or a
pandas DataFrame if that extra is installed.

## Reports, not exceptions

Validation does not raise when data is invalid. A real dataset usually has
several problems at once, and raising on the first turns a single CI run into a
queue of them.

```python
report.is_valid  # bool
report.errors  # violations that invalidate the data
report.warnings  # notable but not invalidating
report.codes()  # ('SPX203', 'SPX205') — for alerting
report.for_feature("age")
report.summary()  # human-readable
report.to_json()  # machine-readable
report.raise_for_status()  # opt into fail-fast
```

## What a violation tells you

Every violation answers what broke, where, how badly, and what to do:

```
ERROR   SPX203 age: Column 'age' has 3 value(s) below the declared min of 18;
        furthest is 12.
        e.g. row 41=12, row 88=15, row 203=17
        fix: Clip or filter the offending rows, or relax min if the data is
             legitimately wider than the contract assumed.
```

The affected count is always exact even though only a few examples are shown —
"3 of 4" and "300,000 of 400,000" call for very different responses.

## Sample values and privacy

Offending values make a report far more actionable, and they are raw data. If
reports are written somewhere that should not hold it — a shared log
aggregator, a public build log — turn them off:

```python
contract.validate(data, sample_values=False)
```

```bash
schemapact validate contract.yaml data.csv --no-samples
```

Counts and codes are still reported; only the values are withheld.

## Order of checks

Structural checks run first: missing columns, undeclared columns, ordering,
types, row counts. Value checks run second, and are **skipped for any column
that failed its type check** — comparing strings against a numeric minimum would
report every row as violating every rule, burying the one problem that matters.

## Warnings

An undeclared column is a warning when `allow_extra_columns` is on, and an error
when it is off. That default surfaces upstream drift before it becomes a
failure. Warnings do not make a report invalid; pass `--fail-on warning` to the
CLI if you want them to fail a build.

## Nulls

What counts as missing is the adapter's job, because it differs by backend:
`None` for mappings, an empty field for CSV, and `NaN`, `None`, `NaT` or `pd.NA`
for pandas. All are treated as null consistently.

Nullability is checked separately from every value-level constraint, so a null
never trips a range or pattern check.
