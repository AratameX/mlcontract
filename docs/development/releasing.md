# Releasing

A PyPI version number can never be reused. Not corrected, not replaced —
a mistaken `0.1.0` means the next release is `0.1.1` and the broken one stays
visible forever. Everything below exists because of that.

## One-time setup

### 1. Trusted Publishing on PyPI

No API tokens are used. GitHub mints a short-lived token proving *this workflow
in this repository* is running, and PyPI verifies it against a publisher you
registered. Nothing long-lived exists to leak.

The project does not exist on PyPI yet, so register a **pending publisher**:

**pypi.org → Account settings → Publishing → Add a new pending publisher**

| Field | Value |
| --- | --- |
| PyPI Project Name | `schemapact` |
| Owner | `AratameX` |
| Repository name | `schemapact` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Repeat on **test.pypi.org** with environment name `testpypi`. The accounts are
separate; registering on one does nothing on the other.

### 2. GitHub environments

**Settings → Environments → New environment**, twice: `pypi` and `testpypi`.
The names must match the workflow and the publisher registrations exactly.

On `pypi`, add yourself under **Required reviewers**. That turns publishing into
a deliberate click rather than a consequence of pushing a tag — which is worth
having on the one action that cannot be undone.

## Every release

### 1. Decide the version

Semantic versioning. If the release changes contracts' behaviour, run the
library's own compatibility check against the previous version's contracts to
confirm the bump is large enough.

### 2. Prepare

```bash
git checkout main && git pull
git checkout -b release-0.1.0
```

- Set the version in `src/schemapact/_version.py`. It is the only place it
  appears; `pyproject.toml` reads it from there.
- Move `CHANGELOG.md`'s `[Unreleased]` entries under `## [0.1.0] - YYYY-MM-DD`,
  and state whether the **Python API** and the **contract format** remain
  compatible.
- Remove the pre-alpha notice from `README.md` if this is the first real release.

### 3. Verify locally

```bash
python scripts/check.py
mkdocs build --strict
python benchmarks/run_all.py        # if any performance claim changed
python -m build && python -m twine check --strict dist/*
```

### 4. Merge, then dry run

Open a pull request, let CI pass, merge it. Then:

**Actions → Publish → Run workflow → testpypi**

That builds, publishes to TestPyPI, and installs the result in a clean
environment to confirm it works. Nothing touches real PyPI.

### 5. Tag

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

The tag must match the package version exactly; the workflow refuses otherwise,
and that check exists because publishing the wrong artifact under the right name
is unfixable.

### 6. Approve

The tag triggers the full pipeline. It builds, publishes to TestPyPI, verifies
the install, and then **waits** for your approval on the `pypi` environment.
Approve it, and the workflow publishes, verifies the published package installs
and runs, and creates the GitHub release with notes taken from the changelog.

### 7. After

```bash
pip install schemapact          # from a machine that has never seen the source
schemapact version
```

Open a pull request setting `_version.py` to the next `.dev0` and adding a fresh
`[Unreleased]` heading.

## When it goes wrong

**Wrong version published.** It cannot be removed in any meaningful sense.
Yank it (`pypi.org → Manage → Yank`), which hides it from resolvers without
breaking anyone who pinned it, and release a fix under a new number.

**Tag pushed by mistake, before publishing succeeded.**

```bash
git push --delete origin v0.1.0
git tag -d v0.1.0
```

Only safe while nothing has been published under it.

**The publish job fails after TestPyPI succeeded.** Fix the cause and re-run
the failed jobs. `skip-existing` means the TestPyPI step tolerates the version
already being there.
