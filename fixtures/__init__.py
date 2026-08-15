"""Canonical Profanex fixtures (API contracts, corpora, perf profiles)."""

from fixtures.loader import (
    FIXTURES_ROOT,
    assert_projection_case,
    build_throughput_corpus,
    filter_from_case,
    load_latency_samples,
    load_suite,
)

__all__ = [
    "FIXTURES_ROOT",
    "assert_projection_case",
    "build_throughput_corpus",
    "filter_from_case",
    "load_latency_samples",
    "load_suite",
]
