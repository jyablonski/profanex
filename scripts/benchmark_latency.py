#!/usr/bin/env python3
"""Single-item latency benchmarks driven by fixtures/perf/latency_samples.yaml."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from fixtures.loader import latency_sample_by_id, load_latency_samples
from profanex import Filter, FilterConfig, __version__


def pct(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def time_call(fn, reps: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        fn()
    out: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1_000_000.0)
    return out


def alpha_id(value: int) -> str:
    """Deterministic base-26 id without digits (leet normalization would fold digits)."""
    chars: list[str] = []
    for _ in range(6):
        value, digit = divmod(value, 26)
        chars.append(chr(ord("a") + digit))
    return "".join(reversed(chars))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=201)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--write", type=Path, default=None)
    parser.add_argument(
        "--list-samples",
        action="store_true",
        help="Print available latency sample ids/tags and exit",
    )
    args = parser.parse_args()

    if args.list_samples:
        for sample in load_latency_samples():
            print(f"{sample.id:<16} tags={sorted(sample.tags)}")
        return

    clean = latency_sample_by_id("clean_prose").text
    matched = latency_sample_by_id("exact_fuck").text
    typo = latency_sample_by_id("fuzzy_typo").text
    phrase = latency_sample_by_id("phrase_blow_job").text
    long_clean = latency_sample_by_id("long_clean").text
    long_dense = latency_sample_by_id("long_dense").text

    exact = Filter()
    fuzzy = Filter(FilterConfig(enable_fuzzy=True, threshold=85, min_fuzzy_len=4))
    cold_ids = [alpha_id(i) for i in range(args.reps + args.warmup)]
    cold_terms = [f"profaneprobe{item}x" for item in cold_ids]
    cold_texts = [f"profaneprobe{item}y" for item in cold_ids]
    cold_fuzzy = Filter(
        FilterConfig(
            banned=cold_terms,
            allowlist=[],
            enable_fuzzy=True,
            threshold=90,
            min_fuzzy_len=4,
        )
    )

    suites = {
        "exact_clean_contains": lambda: exact.contains(clean),
        "exact_matched_contains": lambda: exact.contains(matched),
        "exact_matched_find": lambda: exact.find(matched),
        "exact_matched_clean": lambda: exact.clean(matched),
        "exact_matched_analyze": lambda: exact.analyze(matched),
        "exact_phrase_find": lambda: exact.find(phrase),
        "exact_long_clean_contains": lambda: exact.contains(long_clean),
        "exact_long_dense_find": lambda: exact.find(long_dense),
        "fuzzy_typo_warm_contains": lambda: fuzzy.contains(typo),
        "fuzzy_typo_warm_find": lambda: fuzzy.find(typo),
    }

    rows = []
    print(f"{'suite':<28} {'p50_us':>10} {'p95_us':>10} {'p99_us':>10}")
    for name, fn in suites.items():
        samples = time_call(fn, reps=args.reps, warmup=args.warmup)
        row = {
            "suite": name,
            "p50_us": pct(samples, 50),
            "p95_us": pct(samples, 95),
            "p99_us": pct(samples, 99),
            "mean_us": statistics.fmean(samples),
        }
        rows.append(row)
        print(f"{name:<28} {row['p50_us']:10.2f} {row['p95_us']:10.2f} {row['p99_us']:10.2f}")

    cold_samples: list[float] = []
    for index, text in enumerate(cold_texts):
        t0 = time.perf_counter()
        detected = cold_fuzzy.contains(text)
        elapsed = (time.perf_counter() - t0) * 1_000_000.0
        if not detected:
            raise RuntimeError(f"cold fuzzy probe {index} did not match")
        if index >= args.warmup:
            cold_samples.append(elapsed)
    cold_row = {
        "suite": "fuzzy_unique_cold_contains",
        "p50_us": pct(cold_samples, 50),
        "p95_us": pct(cold_samples, 95),
        "p99_us": pct(cold_samples, 99),
        "mean_us": statistics.fmean(cold_samples),
    }
    rows.append(cold_row)
    print(
        f"{cold_row['suite']:<28} {cold_row['p50_us']:10.2f} "
        f"{cold_row['p95_us']:10.2f} {cold_row['p99_us']:10.2f}"
    )

    payload = {
        "profanex_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "reps": args.reps,
        "warmup": args.warmup,
        "fixture": "fixtures/perf/latency_samples.yaml",
        "results": rows,
    }
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.write}")


if __name__ == "__main__":
    main()
