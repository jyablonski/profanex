#!/usr/bin/env python3
"""Compare public profanity-detection APIs on one deterministic corpus.

This is a product-default benchmark, not a matching-engine microbenchmark. Each
library keeps its packaged English policy and recommended detection API, so hit
counts are reported beside timing results and accuracy is not ranked here.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import platform
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from fixtures.loader import build_throughput_corpus, latency_sample_by_id

INSTALL_COMMAND = (
    "uv run --no-project --python 3.12 --with . --with better-profanity==0.7.0 "
    "--with badwords-py==2.3.1 --with alt-profanity-check==1.9.0 "
    "python -m scripts.benchmark_competitors"
)


@dataclass(frozen=True, slots=True)
class Adapter:
    name: str
    package: str
    version: str
    architecture: str
    contains: Callable[[str], bool]
    contains_many: Callable[[Sequence[str]], list[bool]]


@dataclass(frozen=True, slots=True)
class Result:
    library: str
    package: str
    version: str
    architecture: str
    clean_p50_us: float
    matched_p50_us: float
    batch_median_ms: float
    texts_per_second: float
    detected: int


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"comparison package {name!r} is not installed; run:\n  {INSTALL_COMMAND}"
        ) from exc


def profanex_adapter() -> Adapter:
    from profanex import Filter

    filter_ = Filter()
    return Adapter(
        name="Profanex",
        package="profanex",
        version=package_version("profanex"),
        architecture="Rust rules",
        contains=filter_.contains,
        contains_many=lambda texts: filter_.contains_many(list(texts)),
    )


def better_profanity_adapter() -> Adapter:
    package_version("better-profanity")
    profanity = importlib.import_module("better_profanity").profanity
    profanity.load_censor_words()
    return Adapter(
        name="better-profanity",
        package="better-profanity",
        version=package_version("better-profanity"),
        architecture="Python rules",
        contains=lambda text: bool(profanity.contains_profanity(text)),
        contains_many=lambda texts: [bool(profanity.contains_profanity(text)) for text in texts],
    )


def badwords_adapter() -> Adapter:
    package_version("badwords-py")
    filter_ = importlib.import_module("badwords").ProfanityFilter()
    filter_.init(languages=["en"])
    return Adapter(
        name="BadWords",
        package="badwords-py",
        version=package_version("badwords-py"),
        architecture="Rust rules",
        contains=lambda text: bool(filter_.filter_text(text)),
        contains_many=lambda texts: [bool(filter_.filter_text(text)) for text in texts],
    )


def alt_profanity_check_adapter() -> Adapter:
    package_version("alt-profanity-check")
    predict = importlib.import_module("profanity_check").predict

    return Adapter(
        name="alt-profanity-check",
        package="alt-profanity-check",
        version=package_version("alt-profanity-check"),
        architecture="scikit-learn model",
        contains=lambda text: bool(predict([text])[0]),
        contains_many=lambda texts: [bool(value) for value in predict(list(texts))],
    )


ADAPTERS: dict[str, Callable[[], Adapter]] = {
    "profanex": profanex_adapter,
    "better-profanity": better_profanity_adapter,
    "badwords-py": badwords_adapter,
    "alt-profanity-check": alt_profanity_check_adapter,
}


def median_call_us(fn: Callable[[], object], *, reps: int, warmup: int) -> float:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1_000.0)
    return statistics.median(samples)


def median_batch_ms(fn: Callable[[], object], *, reps: int) -> float:
    samples: list[float] = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0)
    return statistics.median(samples)


def benchmark_adapter(
    adapter: Adapter,
    texts: Sequence[str],
    *,
    reps: int,
    warmup: int,
    batch_reps: int,
) -> Result:
    clean = latency_sample_by_id("clean_prose").text
    matched = latency_sample_by_id("exact_fuck").text
    adapter.contains_many(texts[:100])

    clean_us = median_call_us(lambda: adapter.contains(clean), reps=reps, warmup=warmup)
    matched_us = median_call_us(lambda: adapter.contains(matched), reps=reps, warmup=warmup)
    batch_ms = median_batch_ms(lambda: adapter.contains_many(texts), reps=batch_reps)
    predictions = adapter.contains_many(texts)
    if len(predictions) != len(texts):
        raise RuntimeError(
            f"{adapter.name} returned {len(predictions)} labels for {len(texts)} texts"
        )
    return Result(
        library=adapter.name,
        package=adapter.package,
        version=adapter.version,
        architecture=adapter.architecture,
        clean_p50_us=clean_us,
        matched_p50_us=matched_us,
        batch_median_ms=batch_ms,
        texts_per_second=len(texts) / (batch_ms / 1_000.0),
        detected=sum(predictions),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=5_000)
    parser.add_argument("--profile", default="default_mix")
    parser.add_argument("--reps", type=int, default=201)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--batch-reps", type=int, default=5)
    parser.add_argument(
        "--libraries",
        default=",".join(ADAPTERS),
        help=f"Comma-separated adapters: {', '.join(ADAPTERS)}",
    )
    parser.add_argument("--write", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if args.size < 1 or args.reps < 1 or args.warmup < 0 or args.batch_reps < 1:
        parser.error("size/reps/batch-reps must be positive and warmup must be non-negative")

    requested = [name.strip() for name in args.libraries.split(",") if name.strip()]
    unknown = sorted(set(requested) - ADAPTERS.keys())
    if unknown:
        parser.error(f"unknown libraries: {unknown}")

    texts, corpus = build_throughput_corpus(args.size, profile=args.profile)
    results = [
        benchmark_adapter(
            ADAPTERS[name](),
            texts,
            reps=args.reps,
            warmup=args.warmup,
            batch_reps=args.batch_reps,
        )
        for name in requested
    ]

    print(
        f"Python {platform.python_version()}  {platform.platform()}\n"
        f"profile={corpus['profile']} size={corpus['size']} hash={corpus['corpus_hash']}"
    )
    print()
    print(
        f"{'library':<23} {'version':<10} {'clean p50':>11} {'match p50':>11} "
        f"{'texts/s':>12} {'hits':>7}"
    )
    for result in results:
        print(
            f"{result.library:<23} {result.version:<10} "
            f"{result.clean_p50_us:>9.2f} us {result.matched_p50_us:>9.2f} us "
            f"{result.texts_per_second:>12,.0f} {result.detected:>7}"
        )

    payload = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "reps": args.reps,
        "warmup": args.warmup,
        "batch_reps": args.batch_reps,
        "fixture": "fixtures/perf/throughput_profiles.yaml",
        **corpus,
        "results": [asdict(result) for result in results],
    }
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
