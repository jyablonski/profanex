"""Tests for the reproducible accuracy-report calculations."""

from __future__ import annotations

import random

import pytest
from scripts.evaluate_accuracy import binary_metrics, evaluate_detector
from scripts.evaluate_variation_gaps import generate_variants


def test_binary_metrics() -> None:
    metrics = binary_metrics(
        [True, True, False, False],
        [True, False, True, False],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.false_negatives == 1
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.f1 == pytest.approx(0.5)
    assert metrics.false_positive_rate == pytest.approx(0.5)
    assert metrics.accuracy == pytest.approx(0.5)


def test_binary_metrics_rejects_different_lengths() -> None:
    with pytest.raises(ValueError, match="equal lengths"):
        binary_metrics([True], [])


def test_synthetic_accuracy_corpus_is_deterministic() -> None:
    first = generate_variants(random.Random(20260801), 500)
    second = generate_variants(random.Random(20260801), 500)

    assert first == second
    assert len(first) == 500
    metrics = evaluate_detector(first, lambda text: text == first[0].text)
    assert metrics.total == 500
