#!/usr/bin/env python3
"""Build and enrich a synthetic Polars review DataFrame with Profanex."""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import polars as pl  # ty: ignore[unresolved-import] -- installed ephemerally by the uv command
from profanex import Filter, __version__

CLEAN_REVIEWS = (
    "Excellent quality and quick delivery.",
    "The product works as described and setup was straightforward.",
    "Customer support answered my question promptly.",
    "A dependable purchase with clear instructions.",
)

PROFANE_REVIEWS = (
    "This fucking product failed after one day.",
    "The support experience was absolute shit.",
    "This is a bitch to configure.",
    "What an asshole-designed purchase.",
)


@dataclass(frozen=True, slots=True)
class Timings:
    extract_seconds: float
    analyze_seconds: float
    dataframe_seconds: float

    @property
    def total_seconds(self) -> float:
        return self.extract_seconds + self.analyze_seconds + self.dataframe_seconds


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_reviews(rows: int, profanity_every: int) -> pl.DataFrame:
    texts: list[str] = []
    for review_id in range(rows):
        if review_id % profanity_every == 0:
            template = PROFANE_REVIEWS[(review_id // profanity_every) % len(PROFANE_REVIEWS)]
        else:
            template = CLEAN_REVIEWS[review_id % len(CLEAN_REVIEWS)]
        texts.append(template)

    return pl.DataFrame(
        {
            "id": pl.Series(range(rows), dtype=pl.UInt64),
            "review_text": pl.Series(texts, dtype=pl.String),
        }
    )


def enrich_reviews(
    frame: pl.DataFrame,
    profanity_filter: Filter,
    *,
    parallel: bool,
    workers: int | None,
) -> tuple[pl.DataFrame, Timings]:
    started = time.perf_counter()
    reviews = frame.get_column("review_text").to_list()
    extracted = time.perf_counter()

    contains, cleaned = profanity_filter.analyze_many(reviews, parallel=parallel, workers=workers)
    analyze_finished = time.perf_counter()

    enriched = frame.with_columns(
        pl.Series("contains_profanity", contains, dtype=pl.Boolean),
        pl.Series("review_text_cleaned", cleaned, dtype=pl.String),
    )
    dataframe_finished = time.perf_counter()

    return enriched, Timings(
        extract_seconds=extracted - started,
        analyze_seconds=analyze_finished - extracted,
        dataframe_seconds=dataframe_finished - analyze_finished,
    )


def median(values: list[float]) -> float:
    return statistics.median(values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=positive_int, default=100_000)
    parser.add_argument("--repeats", type=positive_int, default=5)
    parser.add_argument(
        "--profanity-every",
        type=positive_int,
        default=10,
        help="Generate one profane review for every N rows (default: 10)",
    )
    parser.add_argument("--serial", action="store_true", help="Disable parallel batch processing")
    parser.add_argument("--workers", type=positive_int, help="Rayon workers for parallel batches")
    parser.add_argument("--write-parquet", type=Path, help="Optionally write the enriched frame")
    args = parser.parse_args()

    if args.serial and args.workers is not None:
        parser.error("--workers cannot be combined with --serial")

    parallel = not args.serial
    frame = build_reviews(args.rows, args.profanity_every)
    profanity_filter = Filter()

    warmup_rows = min(args.rows, 5_000)
    warmup_texts = frame.get_column("review_text").head(warmup_rows).to_list()
    profanity_filter.analyze_many(warmup_texts, parallel=parallel, workers=args.workers)

    runs: list[Timings] = []
    enriched = frame
    for _ in range(args.repeats):
        enriched, timing = enrich_reviews(
            frame,
            profanity_filter,
            parallel=parallel,
            workers=args.workers,
        )
        runs.append(timing)

    detected = enriched.get_column("contains_profanity").sum()
    expected = (args.rows - 1) // args.profanity_every + 1
    if detected != expected:
        raise RuntimeError(f"expected {expected} profane reviews, detected {detected}")

    if args.write_parquet is not None:
        args.write_parquet.parent.mkdir(parents=True, exist_ok=True)
        enriched.write_parquet(args.write_parquet)

    total = median([run.total_seconds for run in runs])
    print("Profanex + Polars benchmark")
    print(f"Python:             {sys.version.split()[0]}")
    print(f"Profanex:           {__version__}")
    print(f"Polars:             {pl.__version__}")
    print(f"Platform:           {platform.platform()}")
    print(f"Rows:               {args.rows:,}")
    print(f"Profane rows:       {detected:,}")
    print(f"Parallel:           {parallel} (workers={args.workers or 'default'})")
    print(f"Repeats:            {args.repeats}")
    print(f"Column extraction:  {median([run.extract_seconds for run in runs]):.4f} s")
    print(f"analyze_many:       {median([run.analyze_seconds for run in runs]):.4f} s")
    print(f"DataFrame assembly: {median([run.dataframe_seconds for run in runs]):.4f} s")
    print(f"End-to-end median:  {total:.4f} s")
    print(f"Throughput:         {args.rows / total:,.0f} rows/s")
    print("\nSample flagged rows:")
    print(enriched.filter(pl.col("contains_profanity")).head(4))


if __name__ == "__main__":
    main()
