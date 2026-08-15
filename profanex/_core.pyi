from collections.abc import Sequence
from typing import TypeAlias

RawMatch: TypeAlias = tuple[int, int, str, str, int, float, str]

class Engine:
    def __init__(
        self,
        banned: list[dict[str, object]],
        allowlist: list[str],
        *,
        word_boundaries: bool = True,
        normalize_leet: bool = True,
        normalize_repeated_chars: bool = False,
        normalize_separated_runs: bool = False,
        enable_fuzzy: bool = False,
        threshold: float = 85.0,
        min_fuzzy_len: int = 4,
        fuzzy_length_delta: int = 2,
        fuzzy_max_token_len: int = 64,
        mask: str = "stars",
    ) -> None: ...
    def contains(self, text: str) -> bool: ...
    def find(self, text: str) -> list[RawMatch]: ...
    def clean(self, text: str) -> str: ...
    def analyze(self, text: str) -> tuple[bool, str]: ...
    def contains_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[bool]: ...
    def find_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[list[RawMatch]]: ...
    def clean_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[str]: ...
    def analyze_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> tuple[list[bool], list[str]]: ...

__version__: str
