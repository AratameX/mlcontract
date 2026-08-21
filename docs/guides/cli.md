# Command line

```bash
schemapact validate CONTRACT DATA
schemapact diff OLD NEW
schemapact check-compatibility OLD NEW --mode backward|forward|full
schemapact init [--from-csv PATH]
schemapact version
```

## Exit codes

The point of this CLI is to fail a build, so the exit codes are part of its
public interface and will not be renumbered.

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | The data violated the contract |
| `2` | The change is not compatible in the direction requested |
| `3` | Usage error: bad arguments, missing file, unreadable data |
| `4` | The contract itself is invalid |

`1` and `2` are deliberately distinct. "This dataset is bad" and "this schema
change breaks your consumers" call for different responses from a pipeline.

A missing contract file is `3`, not `4` — the contract is absent, not malformed,
and "fix your path" is different advice from "fix your schema".

## validate

```bash
schemapact validate contract.yaml data.csv
schemapact validate contract.yaml data.csv --format json
schemapact validate contract.yaml data.csv --fail-on warning
schemapact validate contract.yaml data.csv --no-samples
schemapact validate contract.yaml data.csv --max-samples 20
```

## diff

```bash
schemapact diff v1.yaml v2.yaml
schemapact diff v1.yaml v2.yaml --require-version-bump
```

Exits `2` on a breaking change, and with `--require-version-bump`, also when the
declared version increment is too small for what changed.

## check-compatibility

```bash
schemapact check-compatibility v1.yaml v2.yaml --mode backward
```

See [Breaking changes](compatibility.md) for what each mode means.

## init

```bash
schemapact init                                  # a commented example
schemapact init --from-csv data.csv              # inferred from real data
schemapact init --from-csv data.csv --infer-ranges
schemapact init --from-csv data.csv -o contracts/input.json --name model_input
```

Inference reads types but not ranges. A bound taken from a sample rejects
legitimate data as soon as something slightly wider arrives, so `--infer-ranges`
is opt-in.

## Machine-readable output

`--format json` is available on `validate`, `diff` and `check-compatibility`.
Errors are written to standard error, so standard output stays valid JSON even
when a command fails:

```bash
schemapact validate contract.yaml data.csv --format json | jq '.violations[].code'
```

## In GitHub Actions

```yaml
- run: pip install "schemapact[yaml,pandas]"

- name: Validate data
  run: schemapact validate contracts/input.yaml data/sample.csv

- name: Contract compatibility
  run: |
    git show origin/main:contracts/input.yaml > /tmp/base.yaml
    schemapact check-compatibility /tmp/base.yaml contracts/input.yaml --mode backward
```
