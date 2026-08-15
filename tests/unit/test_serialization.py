"""Tests for contract serialisation.

The central claim under test: JSON and YAML are two encodings of one
representation. A contract written in either format must produce an identical
object, and neither format may have parsing behaviour the other lacks.
"""

from __future__ import annotations

import json

import pytest

from mlcontract import SPEC_VERSION, Contract, ContractDefinitionError, DType, Feature

yaml = pytest.importorskip("yaml", reason="requires the 'yaml' extra")


def rich_contract() -> Contract:
    """A contract exercising every serialisable field."""
    return Contract(
        name="customer_features",
        version="1.2.3",
        description="Features for the churn model.",
        enforce_column_order=True,
        allow_extra_columns=False,
        min_rows=1,
        max_rows=1_000_000,
        metadata={"team": "risk", "owner": "ml-platform"},
        features=[
            Feature("age", DType.INTEGER, nullable=False, min=18, max=120),
            Feature("income", DType.FLOAT, min=0, max_null_fraction=0.05),
            Feature(
                "country",
                DType.CATEGORICAL,
                allowed_values=["IN", "US", "UK"],
                description="ISO country code.",
            ),
            Feature("email", DType.STRING, pattern=r"^[^@]+@[^@]+$", unique=True),
            Feature("signup", DType.DATETIME, required=False),
            Feature("customer_id", DType.STRING, previous_names=["cust_id", "id"]),
        ],
    )


class TestDictRoundTrip:
    def test_round_trip_preserves_everything(self):
        contract = rich_contract()
        assert Contract.from_dict(contract.to_dict()) == contract

    def test_defaults_are_omitted(self):
        """A contract shows what its author decided, not every available field."""
        data = Contract(
            name="minimal",
            version="1.0.0",
            features=[Feature("a", DType.INTEGER)],
        ).to_dict()

        assert data == {
            "spec_version": SPEC_VERSION,
            "name": "minimal",
            "version": "1.0.0",
            "features": {"a": {"type": "integer"}},
        }

    def test_spec_version_is_always_written(self):
        assert "spec_version" in rich_contract().to_dict()

    def test_feature_order_survives(self):
        contract = rich_contract()
        assert tuple(contract.to_dict()["features"]) == contract.feature_names

    def test_output_is_plain_json_types(self):
        """No tuples or enums may leak out, or encoders would need special cases."""
        json.dumps(rich_contract().to_dict())


class TestJson:
    def test_round_trip(self):
        contract = rich_contract()
        assert Contract.from_json(contract.to_json()) == contract

    def test_output_is_stable(self):
        contract = rich_contract()
        assert contract.to_json() == contract.to_json()

    def test_ends_with_newline(self):
        assert rich_contract().to_json().endswith("\n")

    def test_malformed_json_reports_position(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_json("{not json")
        assert exc.value.code.code == "MLC010"
        assert "line" in str(exc.value)


class TestYaml:
    def test_round_trip(self):
        contract = rich_contract()
        assert Contract.from_yaml(contract.to_yaml()) == contract

    def test_no_python_specific_tags(self):
        """Tuples must not become ``!!python/tuple``; contracts must stay portable."""
        assert "!!python" not in rich_contract().to_yaml()

    def test_uses_block_style(self):
        assert "features:\n" in rich_contract().to_yaml()

    def test_malformed_yaml(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_yaml("features:\n  - [unclosed")
        assert exc.value.code.code == "MLC010"


class TestFormatEquivalence:
    """The guarantee that JSON and YAML are not two contract systems."""

    def test_json_and_yaml_produce_identical_objects(self):
        contract = rich_contract()
        assert Contract.from_json(contract.to_json()) == Contract.from_yaml(contract.to_yaml())

    def test_handwritten_yaml_matches_handwritten_json(self):
        """The same contract, authored by hand in both formats."""
        as_yaml = Contract.from_yaml(
            """
            name: fraud_input
            version: 2.0.0
            features:
              amount:
                type: float
                nullable: false
                min: 0
              currency:
                type: categorical
                allowed_values: [INR, USD]
            """
        )
        as_json = Contract.from_json(
            """
            {
              "name": "fraud_input",
              "version": "2.0.0",
              "features": {
                "amount": {"type": "float", "nullable": false, "min": 0},
                "currency": {"type": "categorical", "allowed_values": ["INR", "USD"]}
              }
            }
            """
        )
        assert as_yaml == as_json

    def test_cross_format_conversion_is_lossless(self):
        contract = rich_contract()
        via_yaml = Contract.from_yaml(Contract.from_json(contract.to_json()).to_yaml())
        assert via_yaml == contract


class TestFiles:
    @pytest.mark.parametrize("suffix", [".json", ".yaml", ".yml"])
    def test_save_and_load(self, tmp_path, suffix):
        contract = rich_contract()
        path = contract.save(tmp_path / f"contract{suffix}")
        assert Contract.load(path) == contract

    def test_load_accepts_a_string_path(self, tmp_path):
        contract = rich_contract()
        path = contract.save(tmp_path / "contract.json")
        assert Contract.load(str(path)) == contract

    def test_unknown_extension_on_save(self, tmp_path):
        with pytest.raises(ContractDefinitionError) as exc:
            rich_contract().save(tmp_path / "contract.txt")
        assert exc.value.code.code == "MLC010"

    def test_unknown_extension_on_load(self, tmp_path):
        path = tmp_path / "contract.txt"
        path.write_text("name: x")
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.load(path)
        assert "Supported extensions" in str(exc.value)

    def test_missing_file(self, tmp_path):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.load(tmp_path / "absent.yaml")
        assert exc.value.code.code == "MLC010"


class TestParsingErrors:
    def test_unknown_contract_key_suggests_a_correction(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict(
                {"name": "x", "version": "1.0.0", "features": {}, "versoin": "1.0.0"}
            )
        assert exc.value.code.code == "MLC002"
        assert "Did you mean 'version'?" in str(exc.value)

    def test_unknown_feature_key_is_not_silently_dropped(self):
        """A misspelled key would otherwise leave a contract looser than it appears."""
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict(
                {
                    "name": "x",
                    "version": "1.0.0",
                    "features": {"age": {"type": "integer", "nullabe": False}},
                }
            )
        assert exc.value.code.code == "MLC002"
        assert "nullable" in str(exc.value)

    @pytest.mark.parametrize("key", ["name", "version", "features"])
    def test_missing_required_keys(self, key):
        document = {"name": "x", "version": "1.0.0", "features": {"a": {"type": "integer"}}}
        del document[key]
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict(document)
        assert exc.value.code.code == "MLC011"

    def test_feature_without_a_type(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict({"name": "x", "version": "1.0.0", "features": {"a": {}}})
        assert exc.value.code.code == "MLC011"

    @pytest.mark.parametrize("document", ["a string", 42, ["a", "list"], None])
    def test_non_mapping_documents(self, document):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict(document)
        assert exc.value.code.code == "MLC010"

    def test_non_mapping_features_section(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict({"name": "x", "version": "1.0.0", "features": ["age"]})
        assert exc.value.code.code == "MLC010"

    def test_non_mapping_feature_body(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict({"name": "x", "version": "1.0.0", "features": {"age": "integer"}})
        assert exc.value.code.code == "MLC010"

    def test_json_document_that_is_not_an_object(self):
        with pytest.raises(ContractDefinitionError):
            Contract.from_json("[1, 2, 3]")

    def test_future_spec_version_is_refused_clearly(self):
        with pytest.raises(ContractDefinitionError) as exc:
            Contract.from_dict(
                {
                    "spec_version": "2",
                    "name": "x",
                    "version": "1.0.0",
                    "features": {"a": {"type": "integer"}},
                }
            )
        assert exc.value.code.code == "MLC003"


class TestFormatSniffing:
    """Decoding without a filename, used when a document arrives as text."""

    def test_json_is_detected_by_its_opening_brace(self):
        from mlcontract.serialization import decode_text

        assert decode_text('{"name": "x"}') == {"name": "x"}

    def test_anything_else_is_treated_as_yaml(self):
        from mlcontract.serialization import decode_text

        assert decode_text("name: x") == {"name": "x"}
