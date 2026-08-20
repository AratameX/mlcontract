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

Figures come from a single desktop under normal background load. Repeated runs
of the same measurement vary by roughly 30%, and occasional outliers run several
times the median — which is why medians are published rather than means. Treat
these as the right order of magnitude rather than precise constants. The
committed result files carry the full environment for anyone who wants to
reproduce or dispute them.

Reproduce with:

```bash
pip install -e ".[dev]" pandera
python benchmarks/run_all.py
```

## Environment for the figures below

Windows 10, AMD64 (Intel), Python 3.11.9, pandas 3.0.5, pandera 0.32.1.

## Validation throughput

| Rows | `list[dict]` | pandas DataFrame |
| ---: | ---: | ---: |
| 1,000 | 3.6 ms | 1.0 ms |
| 10,000 | 35.6 ms | 1.7 ms |
| 100,000 | 364 ms | 7.8 ms |

Roughly 275,000 rows/second through the stdlib adapter and 13 million through
the pandas one.

The gap between them is the point of the adapter protocol. The stdlib adapter
evaluates one value at a time in Python, which is what any backend can do. The
pandas adapter implements the optional vectorised methods, so each check becomes
a single NumPy operation over a whole column. Note also that the pandas path
barely slows as the data grows — 1,000 rows costs 1.0 ms and 100,000 costs 7.8 ms,
because much of that 1.0 ms is fixed overhead rather than per-row work.

## Contract operations

These are the ones that run per-CI-job rather than per-row, and they are
effectively free:

| Operation | Median |
| --- | ---: |
| Construct a contract (10 features) | 0.06 ms |
| `to_dict` (50 features) | 0.05 ms |
| `from_json` (50 features) | 0.33 ms |
| `from_yaml` (50 features) | 8.3 ms |
| Diff (10 features) | 0.04 ms |
| Full compatibility check (10 features) | 0.09 ms |

YAML is roughly 25× slower than JSON to parse. It is the friendlier format to
write by hand and the slower one to load, which is why JSON is the core format
and YAML the optional extra.

## Honest comparison

Same checks, same data, same machine, 100,000 rows:

| Approach | Median | Peak memory | Relative |
| --- | ---: | ---: | ---: |
| Hand-written pandas assertions | 1.6 ms | 0.5 MB | 1× |
| **mlcontract, pandas adapter** | **7.9 ms** | **0.5 MB** | **4.9× slower** |
| pandera, lazy validation | 10.3 ms | 3.6 MB | 6.4× slower |

Hand-written assertions remain the fastest, and always will be: they do nothing
except compute booleans. mlcontract costs about four times as much and returns
structured violations with error codes, affected-row counts, sampled offending
values and remediation text — which is the trade being made, and it is worth
knowing you are making it.

### How it got here

An earlier build measured **45× slower** than hand-written assertions on this
benchmark, and slower than pandera, because value checks iterated in Python one
value at a time.

The fix was not to change the engine. The adapter protocol has an optional
vectorised extension: a backend may implement per-check methods that evaluate a
whole column at once, and the engine falls back to iteration for any it does not
provide. The pandas adapter now implements all five, which is roughly an **11×
speedup and 6× less memory** with no change to the validation logic and no
change to what any report says.

Writing the tests that assert the two paths produce byte-identical reports found
a bug in the *iterating* path: row numbers closed up behind nulls, so every
reported row after the first null pointed at the wrong record.

## Sampling failing values

| Setting | Median (10,000 rows, 10% failing) |
| --- | ---: |
| With samples | 36.2 ms |
| Without samples (`sample_values=False`) | 35.6 ms |

Effectively identical. Turn samples off for privacy, not for speed — the count
of affected rows is computed either way, and only a handful of values are ever
retained.
