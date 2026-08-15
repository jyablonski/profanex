#!/usr/bin/env python3
"""Evaluate Profanex against contract fixtures and a deterministic evasion corpus.

The contract suite is a regression check, not an independent accuracy estimate.
The synthetic suite is useful for comparing Profanex configurations, but its
generated labels and seed vocabulary are not representative production data.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from fixtures.loader import (
    assert_projection_case,
    corpus_hash,
    filter_from_case,
    load_suite,
)
from profanex import Filter, FilterConfig, __version__
from scripts.evaluate_variation_gaps import Variant, generate_variants

DEFAULT_SEED = 20260801
DEFAULT_TARGET = 800


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    """Binary-classification counts and derived rates."""

    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def total(self) -> int:
        return (
            self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        )

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    @property
    def false_positive_rate(self) -> float:
        denominator = self.false_positives + self.true_negatives
        return self.false_positives / denominator if denominator else 0.0

    @property
    def accuracy(self) -> float:
        return (self.true_positives + self.true_negatives) / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            **asdict(self),
            "total": self.total,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "accuracy": self.accuracy,
        }


def binary_metrics(expected: Sequence[bool], predicted: Sequence[bool]) -> BinaryMetrics:
    """Build a confusion matrix from equally sized expected and predicted labels."""
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted labels must have equal lengths")
    tp = fp = tn = fn = 0
    for wanted, got in zip(expected, predicted, strict=True):
        if wanted and got:
            tp += 1
        elif wanted:
            fn += 1
        elif got:
            fp += 1
        else:
            tn += 1
    return BinaryMetrics(tp, fp, tn, fn)


def evaluate_detector(
    variants: Sequence[Variant], detector: Callable[[str], bool]
) -> BinaryMetrics:
    expected = [variant.expected_positive for variant in variants]
    predicted = [bool(detector(variant.text)) for variant in variants]
    return binary_metrics(expected, predicted)


def contract_summary() -> dict[str, int]:
    """Execute the curated contract cases and return their inventory."""
    positive = negative = 0
    for suite in ("corpora/defaults_out_of_box", "corpora/tp", "corpora/fp"):
        for case in load_suite(suite):
            if suite.endswith("/fp"):
                expected = False
            elif "expect_contains" in case:
                expected = bool(case["expect_contains"])
            else:
                expected = bool(case.get("expect"))
            positive += int(expected)
            negative += int(not expected)
            assert_projection_case(case, filter_=filter_from_case(case))
    return {"cases": positive + negative, "positive": positive, "negative": negative}


def accuracy_profiles() -> dict[str, Filter]:
    """Return the supported policy profiles used in the synthetic report."""
    return {
        "default": Filter(),
        "evasion_normalization": Filter(
            FilterConfig(
                normalize_repeated_chars=True,
                normalize_separated_runs=True,
            )
        ),
        "fuzzy_85": Filter(FilterConfig(enable_fuzzy=True, threshold=85)),
        "evasion_plus_fuzzy_85": Filter(
            FilterConfig(
                normalize_repeated_chars=True,
                normalize_separated_runs=True,
                enable_fuzzy=True,
                threshold=85,
            )
        ),
    }


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--write", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    if not 500 <= args.target <= 1000:
        parser.error("--target must be in 500..1000")

    contract = contract_summary()
    variants = generate_variants(random.Random(args.seed), args.target)
    if len(variants) != args.target:
        raise RuntimeError(f"generated {len(variants)} variants, expected {args.target}")

    results = {
        name: evaluate_detector(variants, filter_.contains)
        for name, filter_ in accuracy_profiles().items()
    }

    print(f"Profanex {__version__}  Python {platform.python_version()}")
    print(
        f"Contract fixtures: {contract['cases']} passed "
        f"({contract['positive']} positive, {contract['negative']} negative)"
    )
    print(
        f"Synthetic evasion corpus: {len(variants)} cases, seed={args.seed}, "
        f"hash={corpus_hash([variant.text for variant in variants])}"
    )
    print()
    print(
        f"{'profile':<26} {'precision':>10} {'recall':>9} {'F1':>8} "
        f"{'FP rate':>9} {'TP/FP/TN/FN':>17}"
    )
    for name, metrics in results.items():
        counts = (
            f"{metrics.true_positives}/{metrics.false_positives}/"
            f"{metrics.true_negatives}/{metrics.false_negatives}"
        )
        print(
            f"{name:<26} {pct(metrics.precision):>10} {pct(metrics.recall):>9} "
            f"{pct(metrics.f1):>8} {pct(metrics.false_positive_rate):>9} {counts:>17}"
        )

    payload = {
        "profanex_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "seed": args.seed,
        "variant_count": len(variants),
        "corpus_hash": corpus_hash([variant.text for variant in variants]),
        "contract": contract,
        "profiles": {name: metrics.to_dict() for name, metrics in results.items()},
    }
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
