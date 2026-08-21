"""Contract construction, serialisation and diffing.

These operations happen once per pipeline run rather than once per row, so they
are unlikely to be anyone's bottleneck. They are measured anyway because a
regression here is easy to introduce and impossible to notice: contract loading
sits on the startup path of every CLI invocation and every job.
"""

from __future__ import annotations

import random
from functools import partial

from benchmarks._harness import Suite, announce, measure
from schemapact import Contract, DType, Feature

COUNTRIES = ["IN", "US", "UK", "AU", "CA", "DE", "FR", "JP"]


def build_contract(feature_count: int, *, seed: int = 0) -> Contract:
    """Build a contract with a deterministic mix of feature shapes."""
    rng = random.Random(seed)
    features = []
    for index in range(feature_count):
        kind = index % 4
        if kind == 0:
            features.append(Feature(f"num_{index}", DType.INTEGER, nullable=False, min=0, max=1000))
        elif kind == 1:
            features.append(Feature(f"score_{index}", DType.FLOAT, min=0.0, max=1.0))
        elif kind == 2:
            features.append(
                Feature(
                    f"cat_{index}",
                    DType.CATEGORICAL,
                    allowed_values=rng.sample(COUNTRIES, 4),
                )
            )
        else:
            features.append(Feature(f"text_{index}", DType.STRING, pattern=r"^[a-z]+$"))
    return Contract(name="benchmark", version="1.0.0", features=features)


def run(suite: Suite) -> None:
    """Measure the contract lifecycle."""
    announce("Contract lifecycle")
    group = "contract"

    for size in (10, 100):
        suite.record(
            measure(
                f"construct contract ({size} features)",
                group,
                partial(build_contract, size),
                iterations=50,
            )
        )

    contract = build_contract(50)
    document = contract.to_dict()
    as_json = contract.to_json()

    suite.record(measure("to_dict (50 features)", group, contract.to_dict, iterations=200))
    suite.record(
        measure(
            "from_dict (50 features)",
            group,
            lambda: Contract.from_dict(document),
            iterations=200,
        )
    )
    suite.record(measure("to_json (50 features)", group, contract.to_json, iterations=200))
    suite.record(
        measure(
            "from_json (50 features)",
            group,
            lambda: Contract.from_json(as_json),
            iterations=200,
        )
    )

    try:
        as_yaml = contract.to_yaml()
    except Exception:
        pass
    else:
        suite.record(measure("to_yaml (50 features)", group, contract.to_yaml, iterations=100))
        suite.record(
            measure(
                "from_yaml (50 features)",
                group,
                lambda: Contract.from_yaml(as_yaml),
                iterations=100,
                notes="YAML parsing dominates; JSON is roughly an order faster.",
            )
        )


def run_diff(suite: Suite) -> None:
    """Measure contract comparison."""
    announce("Diff and compatibility")
    group = "diff"

    for size in (10, 100):
        old = build_contract(size, seed=1)
        new = build_contract(size, seed=2)
        suite.record(
            measure(
                f"diff ({size} features)",
                group,
                partial(old.diff, new),
                iterations=100,
            )
        )
        suite.record(
            measure(
                f"compatibility check, full ({size} features)",
                group,
                partial(old.is_compatible_with, new, "full"),
                iterations=100,
                notes="Full mode diffs in both directions, so roughly twice a single diff.",
            )
        )
