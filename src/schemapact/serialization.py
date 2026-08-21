"""Encoding and decoding between plain dictionaries and text.

This module is deliberately ignorant of contracts. It converts mappings to text
and back, and nothing else.

That ignorance is the design. JSON and YAML are two spellings of one
representation, not two contract systems: both decode to a plain dictionary,
which :class:`~schemapact.contract.Contract` then interprets through a single
code path. A contract written in YAML and the same contract written in JSON
therefore produce byte-identical objects, and a bug fixed in one format is
fixed in both because there is only one place to fix it.

YAML support is optional. It requires ``pip install "schemapact[yaml]"``, and
its absence produces actionable guidance rather than a bare ``ImportError``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from schemapact.exceptions import SPX010, ContractDefinitionError, missing_dependency

JSON_SUFFIXES = frozenset({".json"})
"""File extensions read as JSON."""

YAML_SUFFIXES = frozenset({".yaml", ".yml"})
"""File extensions read as YAML."""


def encode_json(data: Mapping[str, Any], *, indent: int = 2) -> str:
    """Render a mapping as JSON text.

    Args:
        data: The mapping to encode.
        indent: Spaces per indentation level.

    Returns:
        JSON text with a trailing newline, key order preserved.
    """
    return json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False) + "\n"


def decode_json(text: str) -> Any:
    """Parse JSON text.

    Args:
        text: The JSON document.

    Returns:
        The decoded value.

    Raises:
        ContractDefinitionError: If the text is not valid JSON. The message
            includes the line and column of the syntax error.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractDefinitionError(
            f"Could not parse JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.",
            code=SPX010,
            line=exc.lineno,
            column=exc.colno,
        ) from exc


def encode_yaml(data: Mapping[str, Any]) -> str:
    """Render a mapping as YAML text.

    Args:
        data: The mapping to encode.

    Returns:
        Block-style YAML with key order preserved.

    Raises:
        IntegrationError: If PyYAML is not installed.
    """
    yaml = _require_yaml()
    return str(
        yaml.safe_dump(
            _plain(data),
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
    )


def decode_yaml(text: str) -> Any:
    """Parse YAML text.

    Uses safe loading, so a contract file can never construct arbitrary Python
    objects. Contracts often arrive from other teams or repositories and are
    treated as untrusted input.

    Args:
        text: The YAML document.

    Returns:
        The decoded value.

    Raises:
        IntegrationError: If PyYAML is not installed.
        ContractDefinitionError: If the text is not valid YAML.
    """
    yaml = _require_yaml()
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractDefinitionError(
            f"Could not parse YAML: {exc}",
            code=SPX010,
        ) from exc


def decode_text(text: str, *, path: Path | str | None = None) -> Any:
    """Decode a document, choosing the format from the file extension.

    Args:
        text: The document contents.
        path: Where it came from. A ``.json`` suffix selects JSON; ``.yaml`` or
            ``.yml`` selects YAML. Without a path, the format is sniffed: text
            starting with ``{`` is JSON, anything else is YAML.

    Returns:
        The decoded value.

    Raises:
        ContractDefinitionError: If the extension is not recognised, or the
            document is malformed.
        IntegrationError: If YAML is needed but PyYAML is not installed.
    """
    if path is None:
        return decode_json(text) if text.lstrip().startswith("{") else decode_yaml(text)

    suffix = Path(path).suffix.lower()
    if suffix in JSON_SUFFIXES:
        return decode_json(text)
    if suffix in YAML_SUFFIXES:
        return decode_yaml(text)

    supported = ", ".join(sorted(JSON_SUFFIXES | YAML_SUFFIXES))
    raise ContractDefinitionError(
        f"Cannot determine the contract format of {path!s}: unrecognised extension "
        f"{suffix!r}. Supported extensions: {supported}.",
        code=SPX010,
        path=str(path),
    )


def encode_for_path(data: Mapping[str, Any], path: Path | str) -> str:
    """Encode a mapping in the format implied by a file extension.

    Args:
        data: The mapping to encode.
        path: Destination path, used only to choose the format.

    Returns:
        The encoded document.

    Raises:
        ContractDefinitionError: If the extension is not recognised.
        IntegrationError: If YAML is needed but PyYAML is not installed.
    """
    suffix = Path(path).suffix.lower()
    if suffix in JSON_SUFFIXES:
        return encode_json(data)
    if suffix in YAML_SUFFIXES:
        return encode_yaml(data)

    supported = ", ".join(sorted(JSON_SUFFIXES | YAML_SUFFIXES))
    raise ContractDefinitionError(
        f"Cannot determine the contract format for {path!s}: unrecognised extension "
        f"{suffix!r}. Supported extensions: {supported}.",
        code=SPX010,
        path=str(path),
    )


def _require_yaml() -> Any:
    """Import PyYAML, or raise an error naming the extra to install."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on install shape
        raise missing_dependency(
            package="PyYAML",
            extra="yaml",
            purpose="Reading and writing YAML contracts",
        ) from exc
    return yaml


def _plain(value: Any) -> Any:
    """Convert to types PyYAML renders cleanly.

    Tuples would otherwise be emitted as ``!!python/tuple`` tags, which are not
    portable and would not survive ``safe_load``.
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
