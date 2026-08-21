"""The community files must stay consistent with the project.

These are the documents people read before deciding whether to trust or
contribute to a library, and they rot silently — a security policy naming a
process that no longer exists, or a contributing guide pointing at a script that
was renamed. Nothing else checks them, so this does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    "README.md",
    "LICENSE",
    "NOTICE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/dependabot.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/workflows/publish.yml",
    "docs/development/releasing.md",
]


@pytest.mark.parametrize("name", REQUIRED)
def test_the_file_exists_and_is_not_empty(name):
    path = ROOT / name
    assert path.is_file(), f"{name} is missing"
    assert path.read_text(encoding="utf-8").strip(), f"{name} is empty"


def test_no_placeholders_survive():
    """A published README containing PLACEHOLDER_GITHUB would be embarrassing."""
    for name in REQUIRED:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "PLACEHOLDER" not in text, f"{name} still contains a placeholder"
        assert "TODO(setup)" not in text, f"{name} still contains a setup TODO"


def test_the_readme_links_to_docs_that_exist():
    """A link to a page that was renamed is worse than no link."""
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\((docs/[^)#]+|examples/[^)#]*|[A-Z_]+\.md)\)", readme)
    missing = [t for t in targets if not (ROOT / t).exists()]
    assert not missing, f"README links to missing paths: {missing}"


def test_contributing_names_the_real_gate():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "scripts/check.py" in text
    assert (ROOT / "scripts" / "check.py").is_file()


def test_the_security_policy_gives_a_private_channel():
    """A policy that only says "open an issue" is not a security policy."""
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
    assert "do not open a public issue" in text
    assert "@" in text or "security/advisories" in text


def test_the_changelog_has_an_unreleased_section():
    """Where the next release's entries accumulate."""
    assert "[Unreleased]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_the_readme_states_the_licence_matching_the_metadata():
    import importlib.metadata as metadata

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    declared = metadata.metadata("schemapact")["License-Expression"]
    assert declared == "Apache-2.0"
    assert "Apache-2.0" in readme
