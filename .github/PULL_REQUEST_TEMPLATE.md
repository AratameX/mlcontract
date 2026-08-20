## What this changes

<!-- The diff shows what changed. Explain why. -->

## Why

<!-- What problem does this solve? Link an issue if there is one. -->

## Checklist

- [ ] `python scripts/check.py` passes
- [ ] New behaviour has tests; fixed bugs have a test that fails without the fix
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Public API change: `EXPECTED_PUBLIC_API` updated in the same commit
- [ ] New error code: `python scripts/generate_error_docs.py` re-run
- [ ] Docs updated if behaviour users depend on has changed

## Compatibility

<!-- Does this change the Python API or the contract file format? If the
     contract format changed, does an older file still load? -->

- [ ] No breaking change
- [ ] Breaking change, described above and in the changelog
