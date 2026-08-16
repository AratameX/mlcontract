# Architecture

```
mlcontract/
├── contract.py        Contract, Feature — the domain model
├── dtypes.py          the canonical type system and widening relation
├── constraints.py     the constraint catalogue, as data
├── serialization.py   JSON and YAML encoders over one representation
├── exceptions.py      the error hierarchy and code registry
├── report.py          ValidationReport, Violation, Severity
├── diff.py            change classification
├── compatibility.py   directional compatibility
├── _protocols.py      the DataSource protocol
├── _engine.py         the validation engine
├── _values.py         null detection, inference, coercion
├── adapters/          mapping, csv, pandas
└── cli/               the command line
```

## The decision everything rests on

**The validation engine imports no data library.** It is written entirely
against the `DataSource` protocol in `_protocols.py`, and every backend —
`list[dict]`, CSV, pandas, later Polars and Arrow — is an adapter implementing
six methods.

Two payoffs. The core stays genuinely dependency-free, which CI verifies rather
than trusts: a job installs no extras and fails if pandas or PyYAML is
importable. And adding a backend later is a small new file rather than a
refactor of validation logic that had quietly grown pandas assumptions.

There is a test that implements a column-oriented source from scratch and
validates through it, so the claim is checked rather than asserted.

## Two versions, deliberately

A contract carries `version` (yours, semantic) and `spec_version` (the file
format's, ours). Conflating them means the format can never evolve without
invalidating every contract already committed to a repository.

## One representation, two encodings

`to_dict()` / `from_dict()` is the canonical layer. JSON and YAML are encoders
sitting on top; neither has parsing logic of its own, so they cannot drift. A
property test asserts that a contract written in either format produces an
identical object.

## Constraints as data

`constraints.py` describes each constraint once: which types it applies to, and
which direction relaxes it. Three separate parts of the library read that table
— contract validation, the engine, and the diff — so they cannot disagree.
Adding a constraint is an entry plus an implementation, not a hunt through three
modules.

## Compatibility in one direction only

Only backward compatibility is implemented. Forward is backward with the
arguments swapped, computed by reversing the diff. One rule set, and no way for
the two directions to disagree.

## Reports, not exceptions

Validation returns a report. Raising loses information: a real dataset has many
problems at once, and you want them all from one run. `raise_for_status()` is
there for callers who want fail-fast.

## Error codes are permanent

Codes are data in `exceptions.py` and are never reused, renumbered or
repurposed, because people grep logs and configure alerts on them. The
[reference page](../reference/errors.md) is generated from the registry by
`scripts/generate_error_docs.py`, and a test fails if it drifts.

## Things deliberately not done

- **No vectorised fast path yet.** Value checks iterate in Python. The fast path
  belongs after benchmarks show where time actually goes; optimising first is
  how you end up with a fast path for something that was never the bottleneck.
- **No inferred renames.** Declared only. See
  [Writing contracts](../guides/contracts.md).
- **No model, prediction or metric contracts.** Deferred to `v0.2`.
