#!/usr/bin/env python3
"""Batch throughput benches driven by fixtures/perf/throughput_profiles.yaml."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from fixtures.loader import build_throughput_corpus
from profanex import Filter, FilterConfig, __version__


def timed_ms(fn, reps: int = 5) -> float:
    samples: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=5000)
    parser.add_argument(
        "--profile",
        default="default_mix",
        help="Profile name from fixtures/perf/throughput_profiles.yaml",
    )
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args()

    texts, corpus_meta = build_throughput_corpus(args.size, profile=args.profile)
    exact = Filter()
    fuzzy = Filter(FilterConfig(enable_fuzzy=True, threshold=85, min_fuzzy_len=4))

    exact.contains_many(texts[:100])
    fuzzy.contains_many(texts[:100])

    results = {
        "exact_contains_serial_ms": timed_ms(lambda: exact.contains_many(texts)),
        "exact_contains_parallel_w2_ms": timed_ms(
            lambda: exact.contains_many(texts, parallel=True, workers=2)
        ),
        "exact_clean_serial_ms": timed_ms(lambda: exact.clean_many(texts)),
        "exact_analyze_serial_ms": timed_ms(lambda: exact.analyze_many(texts)),
        "fuzzy_contains_serial_ms": timed_ms(lambda: fuzzy.contains_many(texts)),
        "fuzzy_contains_parallel_w2_ms": timed_ms(
            lambda: fuzzy.contains_many(texts, parallel=True, workers=2)
        ),
        "fuzzy_analyze_serial_ms": timed_ms(lambda: fuzzy.analyze_many(texts)),
    }

    print(
        f"N={corpus_meta['size']} profile={corpus_meta['profile']} "
        f"corpus_hash={corpus_meta['corpus_hash']}"
    )
    for k, v in results.items():
        thr = args.size / (v / 1000.0) if v > 0 else float("inf")
        print(f"{k:<32} {v:10.3f} ms  ({thr:,.0f} texts/s)")

    payload = {
        "profanex_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "fixture": "fixtures/perf/throughput_profiles.yaml",
        **corpus_meta,
        "results_ms": results,
    }
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.write}")


if __name__ == "__main__":
    main()
