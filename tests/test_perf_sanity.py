"""Algorithmic performance sanity — not a hardware regression gate."""

from __future__ import annotations

import time

from profanex import Filter, FilterConfig


def test_exact_batch_completes_quickly() -> None:
    f = Filter(FilterConfig(banned=["fuck", "shit"], allowlist=[]))
    texts = [f"row {i} fuck now" if i % 2 == 0 else f"clean line {i}" for i in range(5_000)]
    t0 = time.perf_counter()
    out = f.contains_many(texts)
    elapsed = time.perf_counter() - t0
    assert len(out) == 5_000
    assert out[::2] == [True] * 2_500
    assert out[1::2] == [False] * 2_500
    # Shared-runner friendly ceiling; not a published throughput claim.
    assert elapsed < 5.0, f"exact batch too slow: {elapsed:.3f}s"


def test_fuzzy_adversarial_stays_bounded() -> None:
    banned = [f"term{i:03d}" for i in range(500)] + ["target"]
    f = Filter(
        FilterConfig(
            banned=banned,
            allowlist=[],
            enable_fuzzy=True,
            threshold=90,
            fuzzy_max_token_len=64,
        )
    )
    texts = ["zzzzzz", "target", "targat", "x" * 10_000]
    t0 = time.perf_counter()
    _ = f.find_many(texts)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"fuzzy adversarial too slow: {elapsed:.3f}s"
