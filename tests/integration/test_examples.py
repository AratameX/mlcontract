"""Every example is executed here.

An example that is never run stops being documentation and becomes a claim
nobody checks. These tests run each one as a real subprocess and assert on what
it prints, so an API change that breaks an example fails CI in the same commit
that caused it.

Asserting on output rather than just the exit code matters: an example whose
prose still runs but now prints something contradicting its own comments is
worse than one that crashes, because nothing signals it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests._support import requires_pandas

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def run_example(name: str) -> subprocess.CompletedProcess[str]:
    """Execute an example in a fresh interpreter."""
    return subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_examples_directory_is_not_empty():
    """Guards against the path drifting and every test below silently passing."""
    assert sorted(p.name for p in EXAMPLES.glob("*.py"))


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.py")))
def test_every_example_runs_without_error(name):
    result = run_example(name)
    assert result.returncode == 0, result.stderr
    assert not result.stderr, result.stderr


class TestQuickstart:
    def test_reports_clean_and_dirty_data(self):
        output = run_example("01_quickstart.py").stdout
        assert "PASSED" in output
        assert "FAILED" in output

    def test_finds_the_expected_violations(self):
        """Each dirty row breaks a different rule; all must be reported at once."""
        output = run_example("01_quickstart.py").stdout
        for code in ("MLC203", "MLC205", "MLC207"):
            assert code in output


class TestInference:
    def test_infers_types_but_not_ranges(self):
        output = run_example("02_csv_and_inference.py").stdout
        assert "dtype=integer" in output
        assert "min=None" in output

    def test_the_sample_validates_against_its_own_contract(self):
        assert "PASSED" in run_example("02_csv_and_inference.py").stdout


class TestBreakingChanges:
    def test_reports_the_required_bump(self):
        output = run_example("03_breaking_changes.py").stdout
        assert "required bump: major" in output
        assert "sufficient:    False" in output

    def test_backward_and_forward_disagree(self):
        """The whole point of directional compatibility."""
        output = run_example("03_breaking_changes.py").stdout
        assert "INCOMPATIBLE" in output


class TestCiGate:
    def test_a_safe_change_passes_the_gate(self):
        output = run_example("05_ci_gate.py").stdout
        assert "OK: safe to merge." in output

    def test_a_breaking_change_is_rejected(self):
        output = run_example("05_ci_gate.py").stdout
        assert "FAILED: this change breaks existing consumers." in output

    def test_the_gate_exits_zero_for_the_proposed_change(self):
        assert run_example("05_ci_gate.py").returncode == 0


class TestPandasExample:
    @requires_pandas
    def test_shows_the_integer_promotion_behaviour(self):
        """The example's claim about pandas float64 promotion must stay true."""
        output = run_example("04_pandas.py").stdout
        assert "float64" in output
        assert "PASSED" in output

    def test_degrades_gracefully_without_the_extra(self):
        """It must not crash in a core install; it explains what to install."""
        result = run_example("04_pandas.py")
        assert result.returncode == 0
