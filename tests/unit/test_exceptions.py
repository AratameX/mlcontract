"""Tests for the exception hierarchy and error-code registry."""

from __future__ import annotations

import pytest

from mlcontract import ContractDefinitionError, IntegrationError, MLContractError
from mlcontract.exceptions import REGISTRY, ErrorCode, missing_dependency


class TestHierarchy:
    @pytest.mark.parametrize("cls", [ContractDefinitionError, IntegrationError])
    def test_everything_descends_from_the_base(self, cls):
        """Callers must be able to catch MLContractError and get everything."""
        assert issubclass(cls, MLContractError)

    def test_base_is_an_exception(self):
        assert issubclass(MLContractError, Exception)

    def test_definition_error_is_not_an_integration_error(self):
        assert not issubclass(ContractDefinitionError, IntegrationError)


class TestErrorPayload:
    def test_message_carries_the_code(self):
        error = MLContractError("something broke", code=ErrorCode("MLC000", "test"))
        assert str(error) == "[MLC000] something broke"

    def test_context_is_structured(self):
        """Details must be inspectable without parsing the message string."""
        error = MLContractError(
            "bad value", code=ErrorCode("MLC000", "test"), field="age", expected=18
        )
        assert error.context == {"field": "age", "expected": 18}

    def test_message_is_available_without_the_code_prefix(self):
        error = MLContractError("plain", code=ErrorCode("MLC000", "test"))
        assert error.message == "plain"


class TestRegistry:
    def test_codes_are_keyed_by_their_own_identifier(self):
        for key, code in REGISTRY.items():
            assert key == code.code

    def test_every_code_has_a_summary(self):
        for code in REGISTRY.values():
            assert code.summary.strip()

    def test_codes_are_unique(self):
        assert len({code.code for code in REGISTRY.values()}) == len(REGISTRY)

    def test_codes_follow_the_naming_scheme(self):
        for key in REGISTRY:
            assert key.startswith("MLC")
            assert key[3:].isdigit()
            assert len(key) == 6

    def test_error_code_str_is_the_bare_code(self):
        assert str(ErrorCode("MLC001", "x")) == "MLC001"


class TestMissingDependency:
    def test_names_the_exact_install_command(self):
        error = missing_dependency(package="PyYAML", extra="yaml", purpose="Reading YAML")
        assert 'pip install "mlcontract[yaml]"' in str(error)
        assert error.code.code == "MLC901"

    def test_is_an_integration_error(self):
        error = missing_dependency(package="pandas", extra="pandas", purpose="Validating")
        assert isinstance(error, IntegrationError)
        assert error.context == {"package": "pandas", "extra": "pandas"}
