"""Guards the public API surface against accidental change.

``mlcontract.__all__`` is the project's compatibility promise. This test pins it
to an explicit snapshot, so removing or renaming a public symbol cannot happen
as a silent side effect of a refactor — it fails CI and forces the change to be
made deliberately, in the same commit, with a changelog entry.

Adding a symbol requires updating ``EXPECTED_PUBLIC_API`` in the same pull
request. That is the point: the update is the review signal.
"""

from __future__ import annotations

import mlcontract

EXPECTED_PUBLIC_API = frozenset(
    {
        "__version__",
    }
)


def test_public_api_matches_snapshot():
    actual = frozenset(mlcontract.__all__)

    removed = EXPECTED_PUBLIC_API - actual
    added = actual - EXPECTED_PUBLIC_API

    assert not removed, (
        f"Public symbols removed: {sorted(removed)}. This is a breaking change — "
        "it needs a deprecation cycle and a changelog entry."
    )
    assert not added, (
        f"New public symbols: {sorted(added)}. Update EXPECTED_PUBLIC_API and document them."
    )


def test_every_exported_name_resolves():
    for name in mlcontract.__all__:
        assert hasattr(mlcontract, name), f"__all__ advertises {name!r} but it does not exist"


def test_all_is_sorted():
    """Keeps diffs on ``__all__`` readable as the API grows."""
    assert list(mlcontract.__all__) == sorted(mlcontract.__all__)


def test_no_private_names_are_exported():
    leaked = [n for n in mlcontract.__all__ if n.startswith("_") and not n.startswith("__")]
    assert not leaked, f"Private names leaked into the public API: {leaked}"
