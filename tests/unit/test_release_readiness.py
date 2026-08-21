"""Checks that the project is in a releasable state.

A PyPI version number can never be reused, so the cheapest possible moment to
catch a release mistake is before the tag exists. These run on every commit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import mlcontract

ROOT = Path(__file__).resolve().parents[2]

# PEP 440, restricted to the forms this project actually releases.
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.dev\d+)?$")


def pyproject() -> dict[str, Any]:
    """Parse pyproject.toml, skipping on the version floor.

    tomllib arrived in 3.11 and the supported floor is 3.10, so these
    project-level checks are skipped on the oldest version rather than adding a
    dependency for one file. They are not version-specific, so running them
    everywhere else loses nothing.
    """
    tomllib = pytest.importorskip("tomllib", reason="tomllib requires Python 3.11")
    loaded: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return loaded


class TestVersion:
    def test_is_pep440(self):
        assert _VERSION.match(mlcontract.__version__), mlcontract.__version__

    def test_lives_in_exactly_one_place(self):
        """A second version literal would eventually disagree with the first."""
        assert pyproject()["project"]["dynamic"] == ["version"]

    def test_the_installed_metadata_agrees(self):
        import importlib.metadata as metadata

        assert metadata.version("mlcontract") == mlcontract.__version__


class TestTagMatching:
    """The check the publish workflow performs, verified here instead of during a release.

    Tagging v0.1.0 on a package reporting 0.1.0.dev0 would publish the wrong
    artifact under the right name, and that cannot be undone.
    """

    @staticmethod
    def tag_matches(tag: str, version: str) -> bool:
        return tag.removeprefix("v") == version

    @pytest.mark.parametrize(
        ("tag", "version"),
        [("v0.1.0", "0.1.0"), ("v1.2.3", "1.2.3"), ("v0.2.0rc1", "0.2.0rc1")],
    )
    def test_matching_pairs_are_accepted(self, tag, version):
        assert self.tag_matches(tag, version)

    @pytest.mark.parametrize(
        ("tag", "version"),
        [
            ("v0.1.0", "0.1.0.dev0"),  # the mistake this exists to catch
            ("v0.1.0", "0.1.1"),
            ("v0.2.0", "0.1.0"),
            ("0.1.0", "v0.1.0"),
        ],
    )
    def test_mismatched_pairs_are_rejected(self, tag, version):
        assert not self.tag_matches(tag, version)


class TestPackagingMetadata:
    def test_the_console_script_target_is_importable(self):
        """A broken entry point only shows up after someone installs and runs it."""
        target = pyproject()["project"]["scripts"]["mlcontract"]
        module, _, attribute = target.partition(":")
        imported = __import__(module, fromlist=[attribute])
        assert callable(getattr(imported, attribute))

    def test_the_core_declares_no_runtime_dependencies(self):
        assert pyproject()["project"]["dependencies"] == []

    def test_every_extra_group_is_non_empty(self):
        for name, entries in pyproject()["project"]["optional-dependencies"].items():
            assert entries, f"extra {name!r} is empty"

    def test_the_advertised_python_versions_match_the_floor(self):
        """A classifier claiming a version the floor excludes is a broken promise."""
        project = pyproject()["project"]
        floor = project["requires-python"]
        advertised = {
            c.rsplit("::", 1)[1].strip()
            for c in project["classifiers"]
            if c.startswith("Programming Language :: Python :: ") and c[-1].isdigit()
        }
        versions = {v for v in advertised if "." in v}
        assert versions, "no specific Python versions advertised"
        assert floor == ">=3.10"
        assert min(versions, key=lambda v: tuple(map(int, v.split(".")))) == "3.10"

    def test_the_urls_point_at_the_real_repository(self):
        urls = pyproject()["project"]["urls"]
        assert all("AratameX/mlcontract" in url for url in urls.values())


class TestReleaseWorkflow:
    """The workflow is the release process, so a mistake in it is a release bug."""

    @staticmethod
    def workflow() -> dict[str, Any]:
        """Parse the publish workflow, skipping where PyYAML is absent.

        PyYAML is an optional extra, so the core-only CI jobs do not have it.
        These are project-level checks rather than version- or
        dependency-specific ones, so skipping them there loses nothing — and a
        test that cannot run in a dependency-free environment defeats the point
        of having one.
        """
        yaml = pytest.importorskip("yaml", reason="requires the 'yaml' extra")
        loaded: dict[str, Any] = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        )
        return loaded

    def test_it_exists(self):
        assert (ROOT / ".github" / "workflows" / "publish.yml").is_file()

    def test_publishing_requires_a_tag(self):
        jobs = self.workflow()["jobs"]
        assert "refs/tags/" in jobs["pypi"]["if"]

    def test_pypi_comes_after_testpypi_verification(self):
        """Publishing the unfixable one first would defeat having both."""
        needs = self.workflow()["jobs"]["pypi"]["needs"]
        assert "verify-testpypi" in needs

    def test_it_uses_trusted_publishing_not_a_token(self):
        jobs = self.workflow()["jobs"]
        for name in ("pypi", "testpypi"):
            assert jobs[name]["permissions"]["id-token"] == "write"
        raw = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        assert "PYPI_API_TOKEN" not in raw
        assert "password:" not in raw

    def test_the_environments_match_the_publisher_registration(self):
        """These names are configured on PyPI too; a mismatch fails at publish time."""
        jobs = self.workflow()["jobs"]
        assert jobs["pypi"]["environment"]["name"] == "pypi"
        assert jobs["testpypi"]["environment"]["name"] == "testpypi"
