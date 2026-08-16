# Breaking changes

Validating data is table stakes. The question this library exists to answer is
different: **will this change break the people downstream?**

## One idea underneath everything

A change is compatible when every dataset that satisfied the old contract still
satisfies the new one. That is mechanical, constraint by constraint:

- **Relaxing** a rule can only admit more data. Never breaking.
- **Tightening** a rule can only reject data that previously passed. Breaking.

An absent constraint is the loosest possible setting under every rule — no
minimum accepts any value, no pattern accepts any string — which is why *adding*
a constraint is a tightening and removing one is a relaxation.

## Direction matters

"Is this breaking?" has no answer until you ask *for whom*.

| | Question | Ask before |
| --- | --- | --- |
| **backward** | Can the **new** contract read data written for the **old** one? | Deploying a new consumer against existing data |
| **forward** | Can the **old** contract read data written for the **new** one? | Letting a producer upgrade while consumers lag |
| **full** | Both | Producers and consumers upgrade independently |

The asymmetry is the point:

| Change | backward | forward |
| --- | --- | --- |
| Required field added | **breaks** | safe |
| Required field removed | safe | **breaks** |
| Constraint tightened | **breaks** | safe |
| Constraint relaxed | safe | **breaks** |
| Type widened (`integer` → `float`) | safe | **breaks** |
| Description or metadata changed | safe | safe |

A single boolean cannot express any of this, which is why
`is_compatible_with()` takes a mode.

## Using it

```python
changes = v1.diff(v2)

changes.is_breaking  # backward specifically
changes.breaking_changes  # which ones, and why
changes.required_bump  # VersionBump.MAJOR
changes.declared_bump  # VersionBump.PATCH
changes.is_version_bump_sufficient  # False
print(changes.summary())
```

```python
from mlcontract import Compatibility

result = v1.is_compatible_with(v2, Compatibility.FULL)
if not result.is_compatible:
    print(result.summary())
```

## Version bumps

The required bump is *derived* from the changes, never asserted, so it cannot
disagree with them:

- anything tightening → **major**
- anything relaxing → **minor**
- descriptions and metadata only → **patch**

A breaking change shipped as a patch release is how downstream consumers get
broken by an upgrade they had every reason to believe was safe. That check is
one flag:

```bash
mlcontract diff v1.yaml v2.yaml --require-version-bump
```

## In CI

```yaml
- name: Contract compatibility
  run: |
    git show origin/main:contracts/model_input.yaml > /tmp/base.yaml
    mlcontract check-compatibility /tmp/base.yaml contracts/model_input.yaml \
      --mode backward
```

Exit code 2 fails the build. See the [CLI guide](cli.md) for every code.

## Why forward needs no separate rules

Forward compatibility is backward compatibility with the arguments swapped, so
it is computed by reversing the diff. One rule set, one implementation, and no
way for the two directions to disagree as the classification grows. Tests
confirm the equivalence holds rather than merely restating the code.

A consequence worth knowing: forward-breaking changes are described *as their
reverse*, since that is what makes them breaking. Removing a required field
reads as "required feature added" under the forward heading.
