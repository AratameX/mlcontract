"""Tests for the command-line interface.

Exit codes are the CLI's real output — a pipeline reads them, not the prose — so
they are asserted for every command and every failure mode.

Most tests call ``main()`` directly, which is fast and gives real tracebacks. A
handful go through a genuine subprocess, because that is the only way to catch a
broken console-script entry point or a stdout/stderr split that works in-process
and not on a terminal.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mlcontract.cli.main import ExitCode, main
from tests._support import requires_yaml

CSV = """id,age,country,score,signup
1,30,IN,0.91,2026-01-05
2,41,US,0.62,2026-02-11
3,25,IN,0.44,2026-03-02
4,,UK,0.78,2026-03-19
"""

BAD_CSV = """id,age,country,score,signup
1,12,FR,9.9,2026-01-05
"""

CONTRACT: dict[str, Any] = {
    "name": "people",
    "version": "1.0.0",
    "features": {
        "id": {"type": "integer", "nullable": False, "unique": True},
        "age": {"type": "integer", "min": 18},
        "country": {"type": "categorical", "allowed_values": ["IN", "US", "UK"]},
        "score": {"type": "float", "max": 1.0},
        "signup": {"type": "date"},
    },
}


def write_contract(path: Path, **overrides: Any) -> Path:
    """Write CONTRACT as JSON, with shallow overrides applied."""
    document = {**CONTRACT, **overrides}
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def with_feature(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Return the feature map plus one more feature."""
    return {**CONTRACT["features"], name: spec}


def with_constraint(feature: str, **changes: Any) -> dict[str, Any]:
    """Return the feature map with one feature's constraints altered."""
    features = {key: dict(value) for key, value in CONTRACT["features"].items()}
    features[feature].update(changes)
    return features


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A directory holding a contract and both good and bad data."""
    (tmp_path / "people.csv").write_text(CSV, encoding="utf-8")
    (tmp_path / "bad.csv").write_text(BAD_CSV, encoding="utf-8")
    write_contract(tmp_path / "contract.json")
    return tmp_path


def run(*args: Any) -> int:
    """Invoke the CLI in-process and return its exit code."""
    return main([str(arg) for arg in args])


class TestVersion:
    def test_version_command(self, capsys):
        assert run("version") == ExitCode.SUCCESS
        assert "mlcontract" in capsys.readouterr().out

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            run("--version")
        assert exc.value.code == 0
        assert "mlcontract" in capsys.readouterr().out

    def test_no_command_prints_help_and_fails(self, capsys):
        assert run() == ExitCode.USAGE_ERROR
        assert "usage:" in capsys.readouterr().out


class TestValidate:
    def test_clean_data_succeeds(self, workspace, capsys):
        code = run("validate", workspace / "contract.json", workspace / "people.csv")
        assert code == ExitCode.SUCCESS
        assert "PASSED" in capsys.readouterr().out

    def test_violations_exit_one(self, workspace):
        code = run("validate", workspace / "contract.json", workspace / "bad.csv")
        assert code == ExitCode.VALIDATION_FAILED

    def test_text_output_names_the_failing_features(self, workspace, capsys):
        run("validate", workspace / "contract.json", workspace / "bad.csv")
        output = capsys.readouterr().out
        assert "MLC203" in output
        assert "age" in output

    def test_json_output_is_parseable(self, workspace, capsys):
        run("validate", workspace / "contract.json", workspace / "bad.csv", "--format", "json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["is_valid"] is False
        assert payload["contract"]["name"] == "people"

    def test_json_output_lists_codes(self, workspace, capsys):
        run("validate", workspace / "contract.json", workspace / "bad.csv", "--format", "json")
        codes = {v["code"] for v in json.loads(capsys.readouterr().out)["violations"]}
        assert {"MLC203", "MLC204", "MLC205"} <= codes

    def test_no_samples_omits_offending_values(self, workspace, capsys):
        """Offending values are raw data and do not always belong in a build log."""
        run("validate", workspace / "contract.json", workspace / "bad.csv", "--no-samples")
        assert "e.g." not in capsys.readouterr().out

    def test_max_samples_is_respected(self, workspace, capsys):
        run(
            "validate",
            workspace / "contract.json",
            workspace / "bad.csv",
            "--format",
            "json",
            "--max-samples",
            "1",
        )
        for violation in json.loads(capsys.readouterr().out)["violations"]:
            assert len(violation["samples"]) <= 1

    def test_warnings_alone_succeed_by_default(self, workspace, capsys):
        (workspace / "extra.csv").write_text(
            CSV.replace("id,", "unexpected,id,")
            .replace("\n1,", "\nx,1,")
            .replace("\n2,", "\ny,2,")
            .replace("\n3,", "\nz,3,")
            .replace("\n4,", "\nw,4,"),
            encoding="utf-8",
        )
        code = run("validate", workspace / "contract.json", workspace / "extra.csv")
        assert code == ExitCode.SUCCESS
        assert "MLC102" in capsys.readouterr().out

    def test_fail_on_warning_promotes_warnings(self, workspace):
        (workspace / "extra.csv").write_text(
            "id,age,country,score,signup,unexpected\n1,30,IN,0.9,2026-01-05,x\n",
            encoding="utf-8",
        )
        assert (
            run(
                "validate",
                workspace / "contract.json",
                workspace / "extra.csv",
                "--fail-on",
                "warning",
            )
            == ExitCode.VALIDATION_FAILED
        )


class TestValidateErrors:
    def test_missing_contract_is_a_usage_error(self, workspace, capsys):
        """The contract is absent, not malformed — a pipeline needs the difference."""
        code = run("validate", workspace / "nope.json", workspace / "people.csv")
        assert code == ExitCode.USAGE_ERROR
        assert "No such contract file" in capsys.readouterr().err

    def test_missing_data_is_a_usage_error(self, workspace):
        code = run("validate", workspace / "contract.json", workspace / "nope.csv")
        assert code == ExitCode.USAGE_ERROR

    def test_malformed_contract_exits_four(self, workspace, capsys):
        (workspace / "broken.json").write_text(
            json.dumps(
                {"name": "x", "version": "not-a-version", "features": {"a": {"type": "integer"}}}
            ),
            encoding="utf-8",
        )
        code = run("validate", workspace / "broken.json", workspace / "people.csv")
        assert code == ExitCode.INVALID_CONTRACT
        assert "MLC004" in capsys.readouterr().err

    def test_a_directory_is_a_usage_error(self, workspace):
        assert run("validate", workspace, workspace / "people.csv") == ExitCode.USAGE_ERROR

    def test_errors_go_to_stderr_so_stdout_stays_parseable(self, workspace, capsys):
        """A pipeline piping --format json into a parser must not get prose."""
        run("validate", workspace / "nope.json", workspace / "people.csv", "--format", "json")
        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        assert captured.err


class TestDiff:
    @pytest.fixture
    def versions(self, workspace: Path) -> Path:
        write_contract(
            workspace / "v2.json",
            version="1.0.1",
            features=with_constraint("age", min=21),
        )
        write_contract(workspace / "same.json")
        return workspace

    def test_identical_contracts_succeed(self, versions, capsys):
        code = run("diff", versions / "contract.json", versions / "same.json")
        assert code == ExitCode.SUCCESS
        assert "No differences" in capsys.readouterr().out

    def test_breaking_change_exits_two(self, versions):
        code = run("diff", versions / "contract.json", versions / "v2.json")
        assert code == ExitCode.INCOMPATIBLE

    def test_breaking_and_invalid_data_have_different_codes(self, versions):
        """Breaking schema changes and bad data need different responses."""
        breaking = run("diff", versions / "contract.json", versions / "v2.json")
        invalid = run("validate", versions / "contract.json", versions / "bad.csv")
        assert breaking != invalid

    def test_json_output(self, versions, capsys):
        run("diff", versions / "contract.json", versions / "v2.json", "--format", "json")
        payload = json.loads(capsys.readouterr().out)
        assert payload["breaking"] is True
        assert payload["required_bump"] == "major"

    def test_non_breaking_change_succeeds(self, versions, capsys):
        write_contract(
            versions / "relaxed.json",
            version="1.1.0",
            features=with_constraint("age", min=0),
        )
        code = run("diff", versions / "contract.json", versions / "relaxed.json")
        assert code == ExitCode.SUCCESS

    def test_require_version_bump_catches_an_undersized_bump(self, versions):
        write_contract(
            versions / "relaxed.json",
            version="1.0.1",
            features=with_constraint("age", min=0),
        )
        assert run("diff", versions / "contract.json", versions / "relaxed.json") == (
            ExitCode.SUCCESS
        )
        assert (
            run(
                "diff",
                versions / "contract.json",
                versions / "relaxed.json",
                "--require-version-bump",
            )
            == ExitCode.INCOMPATIBLE
        )


class TestCheckCompatibility:
    @pytest.fixture
    def versions(self, workspace: Path) -> Path:
        write_contract(
            workspace / "added.json",
            version="1.1.0",
            features=with_feature("email", {"type": "string"}),
        )
        return workspace

    def test_adding_a_required_field_breaks_backward(self, versions):
        code = run(
            "check-compatibility",
            versions / "contract.json",
            versions / "added.json",
            "--mode",
            "backward",
        )
        assert code == ExitCode.INCOMPATIBLE

    def test_adding_a_required_field_is_forward_safe(self, versions):
        """The same change, the opposite answer — which is the whole point."""
        code = run(
            "check-compatibility",
            versions / "contract.json",
            versions / "added.json",
            "--mode",
            "forward",
        )
        assert code == ExitCode.SUCCESS

    def test_full_requires_both(self, versions):
        code = run(
            "check-compatibility",
            versions / "contract.json",
            versions / "added.json",
            "--mode",
            "full",
        )
        assert code == ExitCode.INCOMPATIBLE

    def test_backward_is_the_default(self, versions, capsys):
        run("check-compatibility", versions / "contract.json", versions / "added.json")
        assert "backward" in capsys.readouterr().out

    def test_identical_contracts_are_compatible(self, versions, capsys):
        code = run("check-compatibility", versions / "contract.json", versions / "contract.json")
        assert code == ExitCode.SUCCESS
        assert "COMPATIBLE" in capsys.readouterr().out

    def test_json_output(self, versions, capsys):
        run(
            "check-compatibility",
            versions / "contract.json",
            versions / "added.json",
            "--format",
            "json",
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["compatible"] is False
        assert payload["mode"] == "backward"

    def test_an_invalid_mode_is_rejected_by_the_parser(self, versions):
        with pytest.raises(SystemExit) as exc:
            run(
                "check-compatibility",
                versions / "contract.json",
                versions / "added.json",
                "--mode",
                "sideways",
            )
        assert exc.value.code == 2  # argparse's own usage exit


class TestInit:
    def test_writes_an_example_without_data(self, tmp_path, capsys):
        target = tmp_path / "contract.json"
        assert run("init", "--output", target) == ExitCode.SUCCESS
        assert target.exists()
        assert "Wrote" in capsys.readouterr().out

    def test_the_example_is_a_valid_contract(self, tmp_path):
        from mlcontract import Contract

        target = tmp_path / "contract.json"
        run("init", "--output", target)
        assert Contract.load(target).name == "my_contract"

    def test_infers_from_csv(self, workspace):
        from mlcontract import Contract, DType

        target = workspace / "inferred.json"
        assert run("init", "--from-csv", workspace / "people.csv", "--output", target) == (
            ExitCode.SUCCESS
        )
        contract = Contract.load(target)
        assert contract["id"].dtype is DType.INTEGER
        assert contract["score"].dtype is DType.FLOAT
        assert contract["signup"].dtype is DType.DATE

    def test_an_inferred_contract_validates_its_own_source(self, workspace):
        """The correctness property that makes inference worth shipping."""
        target = workspace / "inferred.json"
        run("init", "--from-csv", workspace / "people.csv", "--output", target)
        assert run("validate", target, workspace / "people.csv") == ExitCode.SUCCESS

    def test_nullability_is_inferred_from_blanks(self, workspace):
        from mlcontract import Contract

        target = workspace / "inferred.json"
        run("init", "--from-csv", workspace / "people.csv", "--output", target)
        contract = Contract.load(target)
        assert contract["age"].nullable is True
        assert contract["id"].nullable is False

    def test_ranges_are_not_inferred_by_default(self, workspace):
        """A bound read off a sample rejects legitimate data that is slightly wider."""
        from mlcontract import Contract

        target = workspace / "inferred.json"
        run("init", "--from-csv", workspace / "people.csv", "--output", target)
        assert Contract.load(target)["age"].min is None

    def test_ranges_can_be_requested(self, workspace):
        from mlcontract import Contract

        target = workspace / "ranged.json"
        run(
            "init",
            "--from-csv",
            workspace / "people.csv",
            "--output",
            target,
            "--infer-ranges",
        )
        assert Contract.load(target)["age"].min == 25

    def test_name_and_version_are_configurable(self, workspace):
        from mlcontract import Contract

        target = workspace / "named.json"
        run(
            "init",
            "--from-csv",
            workspace / "people.csv",
            "--output",
            target,
            "--name",
            "custom",
            "--contract-version",
            "2.3.4",
        )
        contract = Contract.load(target)
        assert (contract.name, contract.version) == ("custom", "2.3.4")

    def test_refuses_to_overwrite(self, tmp_path, capsys):
        target = tmp_path / "contract.json"
        run("init", "--output", target)
        assert run("init", "--output", target) == ExitCode.USAGE_ERROR
        assert "--force" in capsys.readouterr().err

    def test_force_overwrites(self, tmp_path):
        target = tmp_path / "contract.json"
        run("init", "--output", target)
        assert run("init", "--output", target, "--force") == ExitCode.SUCCESS

    def test_missing_source_is_a_usage_error(self, tmp_path):
        assert run("init", "--from-csv", tmp_path / "nope.csv") == ExitCode.USAGE_ERROR

    def test_json_output_format(self, workspace):
        from mlcontract import Contract

        target = workspace / "inferred.json"
        run("init", "--from-csv", workspace / "people.csv", "--output", target)
        assert Contract.load(target).name == "people"


class TestConsoleScript:
    """A handful of real subprocess runs.

    In-process tests cannot catch a broken entry point in ``pyproject.toml`` or
    an exit code that never reaches the shell, and those are exactly the
    failures a user hits first.
    """

    def invoke(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mlcontract.cli.main", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )

    def test_module_entry_point_runs(self):
        result = self.invoke("version")
        assert result.returncode == 0
        assert "mlcontract" in result.stdout

    def test_help_lists_every_command(self):
        result = self.invoke("--help")
        for command in ("validate", "diff", "check-compatibility", "init", "version"):
            assert command in result.stdout

    def test_help_documents_the_exit_codes(self):
        """They are the interface, so they belong in the help text."""
        assert "Exit codes" in self.invoke("--help").stdout

    def test_exit_code_reaches_the_shell(self, workspace):
        result = self.invoke(
            "validate", str(workspace / "contract.json"), str(workspace / "bad.csv")
        )
        assert result.returncode == ExitCode.VALIDATION_FAILED

    def test_json_on_stdout_is_pipeable(self, workspace):
        result = self.invoke(
            "validate",
            str(workspace / "contract.json"),
            str(workspace / "bad.csv"),
            "--format",
            "json",
        )
        assert json.loads(result.stdout)["is_valid"] is False


class TestErrorHandling:
    def test_a_missing_optional_extra_is_a_usage_error(self, workspace, monkeypatch, capsys):
        """Being told which extra to install beats a bare ImportError."""
        from mlcontract import serialization
        from mlcontract.exceptions import missing_dependency

        def absent(*_: object, **__: object) -> None:
            raise missing_dependency(package="PyYAML", extra="yaml", purpose="Reading YAML")

        monkeypatch.setattr(serialization, "decode_json", absent)
        assert run("validate", workspace / "contract.json", workspace / "people.csv") == (
            ExitCode.USAGE_ERROR
        )
        assert 'pip install "mlcontract[yaml]"' in capsys.readouterr().err

    def test_an_os_error_is_reported_not_traced(self, workspace, monkeypatch, capsys):
        """A permission problem should print one line, not a traceback."""
        import mlcontract.cli.main as cli_main

        def denied(_: object) -> None:
            raise PermissionError(13, "Permission denied", str(workspace / "contract.json"))

        monkeypatch.setattr(cli_main, "_load_contract", denied)
        assert run("validate", workspace / "contract.json", workspace / "people.csv") == (
            ExitCode.USAGE_ERROR
        )
        assert "Permission denied" in capsys.readouterr().err

    def test_unreadable_data_is_a_usage_error(self, workspace):
        (workspace / "data.parquet").write_text("not really parquet", encoding="utf-8")
        assert run("validate", workspace / "contract.json", workspace / "data.parquet") == (
            ExitCode.USAGE_ERROR
        )


class TestInferenceEdgeCases:
    def test_a_small_domain_becomes_categorical(self, tmp_path):
        from mlcontract import Contract, DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("status\n" + "ok\nfail\nok\nok\nfail\nok\n", encoding="utf-8")
        contract: Contract = infer_from_csv(path)
        assert contract["status"].dtype is DType.CATEGORICAL
        assert set(contract["status"].allowed_values or ()) == {"ok", "fail"}

    def test_mostly_unique_text_stays_a_plain_string(self, tmp_path):
        """Otherwise a column of identifiers becomes a closed domain of itself."""
        from mlcontract import DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("ref\n" + "".join(f"ref-{i}\n" for i in range(30)), encoding="utf-8")
        assert infer_from_csv(path)["ref"].dtype is DType.STRING

    def test_an_all_blank_column_defaults_to_string(self, tmp_path):
        """Nothing to go on, so choose the type least likely to reject real data."""
        from mlcontract import DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("a,b\n1,\n2,\n", encoding="utf-8")
        contract = infer_from_csv(path)
        assert contract["b"].dtype is DType.STRING
        assert contract["b"].nullable is True

    def test_booleans_are_recognised(self, tmp_path):
        from mlcontract import DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("flag\ntrue\nfalse\ntrue\n", encoding="utf-8")
        assert infer_from_csv(path)["flag"].dtype is DType.BOOLEAN

    def test_datetimes_are_recognised(self, tmp_path):
        from mlcontract import DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("t\n2026-01-01T10:00:00\n2026-01-02T11:30:00\n", encoding="utf-8")
        assert infer_from_csv(path)["t"].dtype is DType.DATETIME

    def test_categories_can_be_disabled(self, tmp_path):
        from mlcontract import DType
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "d.csv"
        path.write_text("status\nok\nfail\nok\nok\n", encoding="utf-8")
        assert infer_from_csv(path, infer_categories=False)["status"].dtype is DType.STRING


class TestPackageLayout:
    def test_the_main_submodule_is_not_shadowed_by_the_main_function(self):
        """A function named ``main`` must not shadow the ``main`` submodule."""
        import types

        import mlcontract.cli.main as module

        assert isinstance(module, types.ModuleType)

    def test_the_entry_point_target_is_importable(self):
        """Pyproject points the console script at this exact path."""
        from mlcontract.cli.main import run

        assert callable(run)

    def test_run_exits_with_the_returned_code(self, monkeypatch):
        """``run`` must turn the return value into a process exit status."""
        from mlcontract.cli.main import run

        monkeypatch.setattr(sys, "argv", ["mlcontract", "version"])
        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == ExitCode.SUCCESS


@requires_yaml
class TestYamlFormat:
    """The CLI reads and writes YAML when the extra is installed."""

    def test_init_defaults_to_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert run("init") == ExitCode.SUCCESS
        assert (tmp_path / "contract.yaml").exists()

    def test_a_yaml_contract_validates_the_same_data(self, workspace):
        from mlcontract import Contract

        Contract.load(workspace / "contract.json").save(workspace / "contract.yaml")
        assert run("validate", workspace / "contract.yaml", workspace / "people.csv") == (
            ExitCode.SUCCESS
        )

    def test_yaml_and_json_contracts_agree(self, workspace):
        from mlcontract import Contract

        Contract.load(workspace / "contract.json").save(workspace / "contract.yaml")
        assert run("validate", workspace / "contract.yaml", workspace / "bad.csv") == run(
            "validate", workspace / "contract.json", workspace / "bad.csv"
        )


class TestWindowsEncodings:
    """CSVs and contracts written by Windows tools carry a byte-order mark."""

    def test_init_ignores_a_bom_in_the_header(self, tmp_path):
        from mlcontract._inference import infer_from_csv

        path = tmp_path / "people.csv"
        path.write_text("id,age,country\n1,30,IN\n", encoding="utf-8-sig")
        assert infer_from_csv(path).feature_names == ("id", "age", "country")

    def test_the_full_round_trip_survives_a_bom(self, tmp_path, monkeypatch):
        """Init then validate, exactly as a user on Windows would run it."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "people.csv").write_text(
            "id,age,country\n1,30,IN\n2,41,US\n", encoding="utf-8-sig"
        )
        assert run("init", "--from-csv", "people.csv", "--output", "c.json") == (ExitCode.SUCCESS)
        assert run("validate", "c.json", "people.csv") == ExitCode.SUCCESS

    def test_a_contract_file_with_a_bom_loads(self, tmp_path):
        """json.loads rejects a byte-order mark outright."""
        from mlcontract import Contract

        path = tmp_path / "c.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8-sig")
        assert Contract.load(path).name == "people"
