# Performance

Every number here was produced by `python benchmarks/run_all.py` and read out of
the JSON it wrote. None was typed in by hand.

## Methodology

- Median of many timed iterations, after discarding warm-up runs, with garbage
  collection disabled inside each measurement.
- Peak memory sampled with `tracemalloc`.
- Every result file embeds the library version, Python version, OS, CPU and
  dependency versions, so a figure can be checked or fairly disputed.
- Results live in `benchmarks/results/`.

Reproduce with:

```bash
pip install -e ".[dev]" pandera
python benchmarks/run_all.py
```

## Environment for the figures below

Linux x86_64, Python 3.12.3, pandas 3.0.2, pandera 0.32.1.

## Validation throughput

| Rows | `list[dict]` | pandas DataFrame |
| ---: | ---: | ---: |
| 1,000 | 5.0 ms | 2.1 ms |
| 10,000 | 48.8 ms | 3.4 ms |
| 100,000 | 521 ms | 13.3 ms |

Roughly 200,000 rows/second through the stdlib adapter and 7.8 million through
the pandas one.

The gap between them is the point of the adapter protocol. The stdlib adapter
evaluates one value at a time in Python, which is what any backend can do. The
pandas adapter implements the optional vectorised methods, so each check becomes
a single NumPy operation over a whole column. Note also that the pandas path
barely slows as the data grows — 1,000 rows costs 2.1 ms and 100,000 costs 13 ms,
because most of that 2.1 ms is fixed overhead rather than per-row work.

## Contract operations

These are the ones that run per-CI-job rather than per-row, and they are
effectively free:

| Operation | Median |
| --- | ---: |
| Construct a contract (10 features) | 0.08 ms |
| `to_dict` (50 features) | 0.07 ms |
| `from_json` (50 features) | 0.49 ms |
| `from_yaml` (50 features) | 12.9 ms |
| Diff (10 features) | 0.05 ms |
| Full compatibility check (10 features) | 0.11 ms |

YAML is roughly 25× slower than JSON to parse. It is the friendlier format to
write by hand and the slower one to load, which is why JSON is the core format
and YAML the optional extra.

## Honest comparison

Same checks, same data, same machine, 100,000 rows:

| Approach | Median | Peak memory | Relative |
| --- | ---: | ---: | ---: |
| Hand-written pandas assertions | 3.0 ms | 0.5 MB | 1× |
| **mlcontract, pandas adapter** | **12.8 ms** | **0.5 MB** | **4.2× slower** |
| pandera, lazy validation | 15.8 ms | 3.6 MB | 5.2× slower |

Hand-written assertions remain the fastest, and always will be: they do nothing
except compute booleans. mlcontract costs about four times as much and returns
structured violations with error codes, affected-row counts, sampled offending
values and remediation text — which is the trade being made, and it is worth
knowing you are making it.

### How it got here

An earlier release measured **154 ms** on this benchmark, 45× slower than
hand-written assertions and 8.6× slower than pandera, because value checks
iterated in Python one value at a time.

The fix was not to change the engine. The adapter protocol has an optional
vectorised extension: a backend may implement per-check methods that evaluate a
whole column at once, and the engine falls back to iteration for any it does not
provide. The pandas adapter now implements all five, which is a **12× speedup
and 6× less memory** with no change to the validation logic and no change to
what any report says.

Writing the tests that assert the two paths produce byte-identical reports found
a bug in the *iterating* path: row numbers closed up behind nulls, so every
reported row after the first null pointed at the wrong record.

## Sampling failing values

| Setting | Median (10,000 rows, 10% failing) |
| --- | ---: |
| With samples | 61.8 ms |
| Without samples (`sample_values=False`) | 61.3 ms |

Effectively identical. Turn samples off for privacy, not for speed — the count
of affected rows is computed either way, and only a handful of values are ever
retained.
