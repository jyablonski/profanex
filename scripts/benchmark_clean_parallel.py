from __future__ import annotations

import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable

from profanex import ProfanityFilter


def load_reviews(filepath: str) -> list[str]:
    """Read one review per line from *filepath*."""
    return Path(filepath).read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# Worker‑side logic
# ---------------------------------------------------------------------------
def _init_worker() -> None:
    """Create a ProfanityFilter instance *once* per worker process."""
    global _PF
    _PF = ProfanityFilter()


def _clean_review(text: str) -> str:
    """Return the cleaned version of the review."""
    return _PF.clean(text)  # type: ignore[name-defined]


# ---------------------------------------------------------------------------
# Parallel benchmark
# ---------------------------------------------------------------------------
def benchmark_parallel_clean(
    reviews: Iterable[str], max_workers: int | None = None
) -> None:
    """Clean reviews in parallel and print timing statistics."""
    start = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=max_workers or mp.cpu_count(),
        initializer=_init_worker,
    ) as pool:
        cleaned_reviews = list(pool.map(_clean_review, reviews, chunksize=100))

    duration = time.perf_counter() - start
    total = len(cleaned_reviews)

    print(
        f"Cleaned {total} reviews in {duration:.2f}s "
        f"({duration / total:.6f}s per review)"
    )
    # Optional: write cleaned output
    Path("scripts/cleaned_reviews.txt").write_text(
        "\n".join(cleaned_reviews), encoding="utf-8"
    )


if __name__ == "__main__":
    reviews = load_reviews("scripts/sample_reviews.txt")
    benchmark_parallel_clean(reviews)
