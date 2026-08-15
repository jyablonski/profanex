#!/usr/bin/env python3
"""Measure serial vs parallel batch crossover using the `crossover` perf profile."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

from fixtures.loader import build_throughput_corpus
from profanex import Filter, FilterConfig


def timed(fn, reps: int = 7) -> float:
    samples: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples)


def main() -> None:
    f = Filter(FilterConfig(banned=["fuck", "shit", "ass"], allowlist=[]))
    sizes = [50, 200, 1000, 5000, 20000]
    rows: list[str] = []
    print(f"{'N':>8} {'serial_ms':>12} {'par_w2_ms':>12} {'par_default_ms':>14} {'speedup_w2':>10}")
    for n in sizes:
        texts, _meta = build_throughput_corpus(n, profile="crossover")
        f.contains_many(texts)
        f.contains_many(texts, parallel=True, workers=2)

        serial = timed(lambda t=texts: f.contains_many(t))
        par2 = timed(lambda t=texts: f.contains_many(t, parallel=True, workers=2))
        pard = timed(lambda t=texts: f.contains_many(t, parallel=True))
        speed = serial / par2 if par2 > 0 else float("inf")
        print(f"{n:8d} {serial:12.3f} {par2:12.3f} {pard:14.3f} {speed:10.2f}x")
        rows.append(f"| {n} | {serial:.3f} | {par2:.3f} | {pard:.3f} | speedup_w2={speed:.2f}x |")

    out = Path(__file__).resolve().parents[1] / "docs" / "benchmarks.md"
    block = "\n".join(
        [
            "",
            "### Auto-recorded run",
            "",
            "Corpus profile: `crossover` (`fixtures/perf/throughput_profiles.yaml`).",
            "",
            "| N texts | serial ms | parallel(workers=2) ms | parallel(default) ms | notes |",
            "|---|---:|---:|---:|---|",
            *rows,
            "",
        ]
    )
    text = out.read_text(encoding="utf-8")
    marker = "### Auto-recorded run"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n" + block
    else:
        text = text.rstrip() + "\n" + block
    out.write_text(text, encoding="utf-8")
    print(f"\nUpdated {out}")


if __name__ == "__main__":
    main()
