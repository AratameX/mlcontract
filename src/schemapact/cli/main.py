"""The ``schemapact`` command-line interface.

The point of this CLI is to fail a build. Everything else it prints is
secondary, which is why the exit codes are treated as part of the public
interface and tested as carefully as the Python API:

=====  ======================================================================
Code   Meaning
=====  ======================================================================
``0``  Success. No violations, no breaking changes.
``1``  The data violated the contract.
``2``  The contract change is not compatible in the direction requested.
``3``  Usage error: bad arguments, missing file, unreadable data.
``4``  The contract itself is invalid.
=====  ======================================================================

``1`` and ``2`` are deliberately distinct. "This dataset is bad" and "this
schema change will break your consumers" call for different responses from a
pipeline, and collapsing them into a single failure code would make that
impossible to express.

``argparse`` from the standard library is used rather than a CLI framework.
Five commands do not justify a dependency in a package whose core has none.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from enum import IntEnum
from pathlib import Path
from typing import Any

from schemapact._version import __version__
from schemapact.compatibility import Compatibility
from schemapact.contract import Contract
from schemapact.exceptions import (
    ContractDefinitionError,
    ContractValidationError,
    SchemaPactError,
)


class UsageError(Exception):
    """A problem with the invocation rather than with any contract or data."""


class ExitCode(IntEnum):
    """Process exit codes. Part of the public interface — never renumber."""

    SUCCESS = 0
    VALIDATION_FAILED = 1
    INCOMPATIBLE = 2
    USAGE_ERROR = 3
    INVALID_CONTRACT = 4


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code.

    Args:
        argv: Arguments to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        One of :class:`ExitCode`.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return ExitCode.USAGE_ERROR

    handlers = {
        "validate": _validate,
        "diff": _diff,
        "check-compatibility": _check_compatibility,
        "init": _init,
        "version": _version,
    }

    try:
        return handlers[args.command](args)
    except UsageError as error:
        _fail(str(error))
        return ExitCode.USAGE_ERROR
    except ContractDefinitionError as error:
        _fail(str(error))
        return ExitCode.INVALID_CONTRACT
    except ContractValidationError as error:
        # Only reaches here when the *data* could not be read at all, which is a
        # problem with the invocation rather than with the data's contents.
        _fail(str(error))
        return ExitCode.USAGE_ERROR
    except SchemaPactError as error:
        _fail(str(error))
        return ExitCode.USAGE_ERROR
    except OSError as error:
        _fail(f"{error.strerror or error}: {getattr(error, 'filename', '')}".strip(": "))
        return ExitCode.USAGE_ERROR


def run() -> None:
    """Console-script entry point."""
    sys.exit(main())


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _load_contract(path: str) -> Contract:
    """Load a contract, distinguishing "not there" from "not valid".

    A missing file is a usage error: the contract is absent, not malformed. A
    pipeline needs to tell those apart, because one means fix your path and the
    other means fix your schema.
    """
    location = Path(path)
    if not location.exists():
        raise UsageError(f"No such contract file: {location}")
    if location.is_dir():
        raise UsageError(f"{location} is a directory, not a contract file.")
    return Contract.load(location)


def _validate(args: argparse.Namespace) -> int:
    """Check data against a contract."""
    contract = _load_contract(args.contract)
    report = contract.validate(
        args.data,
        sample_values=not args.no_samples,
        max_samples=args.max_samples,
    )

    _emit(report.to_json() if args.format == "json" else report.summary())

    if report.errors:
        return ExitCode.VALIDATION_FAILED
    if args.fail_on == "warning" and report.warnings:
        return ExitCode.VALIDATION_FAILED
    return ExitCode.SUCCESS


def _diff(args: argparse.Namespace) -> int:
    """Show what changed between two contract versions."""
    changes = _load_contract(args.old).diff(_load_contract(args.new))

    _emit(changes.to_json() if args.format == "json" else changes.summary())

    if changes.is_breaking:
        return ExitCode.INCOMPATIBLE
    if args.require_version_bump and not changes.is_version_bump_sufficient:
        return ExitCode.INCOMPATIBLE
    return ExitCode.SUCCESS


def _check_compatibility(args: argparse.Namespace) -> int:
    """Check whether a contract change is safe in a given direction."""
    result = _load_contract(args.old).is_compatible_with(
        _load_contract(args.new), Compatibility(args.mode)
    )

    _emit(result.to_json() if args.format == "json" else result.summary())
    return ExitCode.SUCCESS if result.is_compatible else ExitCode.INCOMPATIBLE


def _init(args: argparse.Namespace) -> int:
    """Write a starting contract, optionally inferred from existing data."""
    from schemapact import _inference

    if args.from_csv and not Path(args.from_csv).exists():
        raise UsageError(f"No such data file: {args.from_csv}")

    if args.from_csv:
        contract = _inference.infer_from_csv(
            args.from_csv,
            name=args.name,
            version=args.contract_version,
            infer_ranges=args.infer_ranges,
        )
    else:
        contract = _example_contract(args.name or "my_contract", args.contract_version)

    destination = Path(args.output)
    if destination.exists() and not args.force:
        _fail(f"{destination} already exists. Pass --force to overwrite it.")
        return ExitCode.USAGE_ERROR

    contract.save(destination)
    _emit(f"Wrote {destination} with {len(contract)} feature(s).")
    if args.from_csv:
        _emit(
            "Inferred from a sample, so review it: types generalise well, but "
            "categories and nullability describe the rows that happened to be in "
            "the file."
        )
    return ExitCode.SUCCESS


def _version(_: argparse.Namespace) -> int:
    """Print the installed version."""
    _emit(f"schemapact {__version__}")
    return ExitCode.SUCCESS


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Exposed separately so tests and documentation tooling can inspect it without
    running anything.
    """
    parser = argparse.ArgumentParser(
        prog="schemapact",
        description="Versioned data contracts. Validate data and catch breaking schema changes.",
        epilog=(
            "Exit codes: 0 success, 1 data violated the contract, "
            "2 incompatible change, 3 usage error, 4 invalid contract."
        ),
    )
    parser.add_argument("--version", action="version", version=f"schemapact {__version__}")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    validate = commands.add_parser(
        "validate",
        help="check data against a contract",
        description="Check a dataset against a contract.",
    )
    validate.add_argument("contract", help="path to the contract (.yaml, .yml or .json)")
    validate.add_argument("data", help="path to the data (.csv or .tsv)")
    _add_format(validate)
    validate.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        default="error",
        help="treat warnings as failures too (default: error)",
    )
    validate.add_argument(
        "--no-samples",
        action="store_true",
        help="omit offending values from the output, which may contain personal data",
    )
    validate.add_argument(
        "--max-samples",
        type=int,
        default=5,
        metavar="N",
        help="how many offending values to show per violation (default: 5)",
    )

    diff = commands.add_parser(
        "diff",
        help="show what changed between two contract versions",
        description="Compare two versions of a contract.",
    )
    diff.add_argument("old", help="the earlier contract")
    diff.add_argument("new", help="the later contract")
    _add_format(diff)
    diff.add_argument(
        "--require-version-bump",
        action="store_true",
        help="also fail when the declared version increment is too small for the changes",
    )

    compatibility = commands.add_parser(
        "check-compatibility",
        help="check whether a contract change is safe",
        description=(
            "Check whether moving from one contract to another is compatible. "
            "backward: can the new contract read old data? forward: can the old "
            "contract read new data? full: both."
        ),
    )
    compatibility.add_argument("old", help="the earlier contract")
    compatibility.add_argument("new", help="the later contract")
    compatibility.add_argument(
        "--mode",
        choices=[mode.value for mode in Compatibility],
        default=Compatibility.BACKWARD.value,
        help="which direction to check (default: backward)",
    )
    _add_format(compatibility)

    init = commands.add_parser(
        "init",
        help="write a starting contract",
        description="Create a contract, optionally inferred from an existing CSV.",
    )
    init.add_argument(
        "--from-csv",
        metavar="PATH",
        help="infer the contract from this file instead of writing an example",
    )
    init.add_argument(
        "--output",
        "-o",
        default="contract.yaml",
        metavar="PATH",
        help="where to write it (default: contract.yaml)",
    )
    init.add_argument("--name", help="contract name (default: the data file's stem)")
    init.add_argument(
        "--contract-version", default="0.1.0", metavar="VERSION", help="starting version"
    )
    init.add_argument(
        "--infer-ranges",
        action="store_true",
        help="read min and max from the sample; off by default because observed "
        "bounds reject legitimate data that happens to be slightly wider",
    )
    init.add_argument("--force", action="store_true", help="overwrite an existing file")

    commands.add_parser("version", help="print the installed version")

    return parser


def _add_format(parser: argparse.ArgumentParser) -> None:
    """Add the shared output-format option."""
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _emit(text: str) -> None:
    """Write to standard output."""
    print(text)


def _fail(message: str) -> None:
    """Write an error to standard error.

    Errors go to stderr so that ``--format json`` output on stdout stays valid
    JSON even when something goes wrong, which is what lets a pipeline pipe it
    straight into a parser.
    """
    print(f"error: {message}", file=sys.stderr)


def _example_contract(name: str, version: str) -> Any:
    """Build a small illustrative contract for ``init`` with no data file."""
    from schemapact.contract import Feature
    from schemapact.dtypes import DType

    return Contract(
        name=name,
        version=version,
        description="Replace these features with the ones your data actually has.",
        features=[
            Feature(
                "id",
                DType.INTEGER,
                nullable=False,
                unique=True,
                description="A unique identifier.",
            ),
            Feature(
                "amount",
                DType.FLOAT,
                min=0,
                description="A numeric feature with a lower bound.",
            ),
            Feature(
                "category",
                DType.CATEGORICAL,
                allowed_values=["a", "b", "c"],
                description="A feature drawn from a known set of values.",
            ),
        ],
    )


if __name__ == "__main__":  # pragma: no cover
    run()
