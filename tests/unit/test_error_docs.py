"""The error-code reference must match the registry.

The page is rendered from `mlcontract.exceptions.REGISTRY`, so it cannot claim a
code that does not exist. It can still go stale the other way — someone adds a
code and forgets to regenerate — and documentation that silently omits a code
people will see in their logs is worse than none.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from mlcontract.exceptions import REGISTRY

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_error_docs.py"
REFERENCE = ROOT / "docs" / "reference" / "errors.md"


def test_the_reference_exists():
    assert REFERENCE.is_file(), f"Run: python {GENERATOR.relative_to(ROOT)}"


def test_the_reference_is_up_to_date():
    """The same check CI runs, so a stale page fails here first."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_registered_code_is_documented():
    text = REFERENCE.read_text(encoding="utf-8")
    missing = [code for code in REGISTRY if f"`{code}`" not in text]
    assert not missing, f"Undocumented codes: {sorted(missing)}"


def test_no_code_is_documented_that_does_not_exist():
    """Guards against a hand-edit that invents a code."""
    import re

    text = REFERENCE.read_text(encoding="utf-8")
    documented = set(re.findall(r"`(MLC\d{3})`", text))
    assert documented - set(REGISTRY) == set()


def test_the_page_says_it_is_generated():
    """So nobody edits it by hand and loses the change on the next run."""
    assert "Do not edit by hand" in REFERENCE.read_text(encoding="utf-8")
