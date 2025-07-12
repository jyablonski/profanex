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


def _init_worker() -> None:
    """Create a ProfanityFilter instance *once* per worker process."""
    global _PF
    _PF = ProfanityFilter()


def _check_review(text: str) -> bool:
    """Return True if the review contains profanity (uses global _PF)."""
    return _PF.has_profanity(text=text)


def benchmark_parallel(reviews: Iterable[str], max_workers: int | None = None) -> None:
    """Check reviews in parallel and print timing statistics."""
    start = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=max_workers or mp.cpu_count(),
        initializer=_init_worker,
    ) as pool:
        profane_flags = list(pool.map(_check_review, reviews, chunksize=100))

    duration = time.perf_counter() - start
    flagged = sum(profane_flags)

    total = len(profane_flags)
    print(
        f"Checked {total} reviews in {duration:.2f}s "
        f"({duration / total:.6f}s per review)"
    )
    print(f"Flagged {flagged} reviews as profane")


if __name__ == "__main__":
    reviews = load_reviews("scripts/sample_reviews.txt")
    benchmark_parallel(reviews)
