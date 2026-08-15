"""Public Profanex API types."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeVar, cast

from profanex.lexicon import (
    Category,
    ConfigError,
    LexiconData,
    categories_from_bits,
    load_effective_lexicon,
)
from profanex.masks import SUPPORTED_MASKS, MaskName, validate_mask


def _snapshot_banned(
    data: Collection[str] | Mapping[str, Collection[str]] | None,
    *,
    source: str,
) -> tuple[str, ...] | Mapping[str, tuple[str, ...]] | None:
    if data is None:
        return None
    if isinstance(data, (str, bytes, bytearray)):
        raise ConfigError(
            f"banned lexicon in {source} must be a list or mapping, not a bare string"
        )
    if isinstance(data, Mapping):
        out: dict[str, tuple[str, ...]] = {}
        for key, words in data.items():
            if isinstance(words, (str, bytes, bytearray)) or not isinstance(words, Iterable):
                raise ConfigError(f"category {key!r} in {source} must be an iterable of terms")
            category_key = key.value if isinstance(key, Category) else str(key)
            out[category_key] = _snapshot_terms(words, source=f"category {key!r} in {source}")
        return MappingProxyType(out)
    if not isinstance(data, Iterable):
        raise ConfigError(f"banned lexicon in {source} must be an iterable or mapping")
    return _snapshot_terms(data, source=source)


def _snapshot_terms(data: Iterable[object], *, source: str) -> tuple[str, ...]:
    out: list[str] = []
    for item in data:
        if not isinstance(item, str):
            raise ConfigError(f"terms in {source} must be str, got {type(item)!r}")
        out.append(item)
    return tuple(out)


def _snapshot_allowlist(data: Collection[str] | None, *, source: str) -> tuple[str, ...] | None:
    if data is None:
        return None
    if isinstance(data, (str, bytes, bytearray)):
        raise ConfigError(f"allowlist in {source} must be a list or mapping, not a bare string")
    if isinstance(data, Mapping):
        raise ConfigError(
            f"allowlist in {source} must be a sequence of terms, not a mapping; "
            "use allowlist_path / YAML for category-shaped allowlists"
        )
    return _snapshot_terms(data, source=source)


@dataclass(frozen=True, slots=True)
class Match:
    """One accepted, non-overlapping profanity match.

    Attributes:
        start: Inclusive start index in the original Python string.
        end: Exclusive end index in the original Python string.
        text: Exact slice from the original string. Always equals
            ``source[start:end]`` for the source passed to ``Filter.find``.
        term: Canonical term from the effective banned lexicon.
        categories: Enabled policy categories associated with ``term``.
        score: Similarity from 0 through 100. Exact and phrase matches use 100.
        kind: Matching path: ``"exact"``, ``"phrase"``, or ``"fuzzy"``.
    """

    start: int
    end: int
    text: str
    term: str
    categories: frozenset[Category]
    score: float
    kind: Literal["exact", "phrase", "fuzzy"]


MaskFn = Callable[[str, list[Match]], str]
MaskSpec = MaskName | MaskFn
_T = TypeVar("_T")

# Keep configurable fuzzy work inside a predictable per-token envelope. The Rust
# engine also validates these limits so direct private-extension callers cannot
# bypass the public API guardrails.
MAX_FUZZY_LENGTH_DELTA = 64
MAX_FUZZY_TOKEN_LEN = 256


def _validate_mask_spec(mask: object) -> None:
    if isinstance(mask, str):
        validate_mask(mask)
        return
    if callable(mask):
        return
    raise ConfigError(
        f"mask must be one of {sorted(SUPPORTED_MASKS)} or a callable, got {type(mask)!r}"
    )


@dataclass(frozen=True, slots=True)
class FilterConfig:
    """Immutable filter policy.

    Numeric knobs, mask, categories, mutual exclusion, and in-memory lexicon
    container shapes are validated eagerly. YAML path contents are validated when
    constructing a ``Filter``.

    Attributes:
        categories: Enabled categories, or ``None`` to enable every category.
        banned: In-memory replacement banned lexicon. Flat terms use ``general``
            when enabled, otherwise the selected categories.
        banned_path: YAML replacement banned lexicon path.
        extra_banned: Terms merged into the selected banned lexicon. Flat terms
            use the same category assignment as ``banned``.
        extra_banned_path: YAML terms merged into the selected banned lexicon.
        allowlist: In-memory replacement allowlist.
        allowlist_path: YAML replacement allowlist path.
        extra_allowlist: Terms merged into the selected allowlist.
        extra_allowlist_path: YAML terms merged into the selected allowlist.
        threshold: Minimum fuzzy similarity score from 0 through 100.
        enable_fuzzy: Whether to run optional single-token fuzzy matching.
        min_fuzzy_len: Minimum normalized token and term length for fuzzy matching.
        fuzzy_length_delta: Maximum token/term length difference considered by fuzzy matching,
            from 0 through 64.
        fuzzy_max_token_len: Maximum token length considered by fuzzy matching, capped at 256.
        word_boundaries: Whether accepted matches must satisfy Unicode word boundaries.
        mask: Built-in mask name or serial Python callback.
        normalize_leet: Whether to normalize the built-in leetspeak substitutions.
        normalize_separated_runs: Whether to join guarded separated character runs.
        normalize_repeated_chars: Whether to collapse character runs of length three or more.

    Raises:
        ConfigError: If an option has the wrong type or range, mutually exclusive
            sources are combined, or an in-memory lexicon has an invalid shape.
    """

    categories: frozenset[Category] | None = None
    banned: Collection[str] | Mapping[str, Collection[str]] | None = None
    banned_path: str | None = None
    extra_banned: Collection[str] | Mapping[str, Collection[str]] | None = None
    extra_banned_path: str | None = None
    allowlist: Collection[str] | None = None
    allowlist_path: str | None = None
    extra_allowlist: Collection[str] | None = None
    extra_allowlist_path: str | None = None
    threshold: int = 85
    enable_fuzzy: bool = False
    min_fuzzy_len: int = 4
    fuzzy_length_delta: int = 2
    fuzzy_max_token_len: int = 64
    word_boundaries: bool = True
    mask: MaskSpec = "stars"
    normalize_leet: bool = True
    normalize_separated_runs: bool = False
    normalize_repeated_chars: bool = False

    def __post_init__(self) -> None:
        if self.banned is not None and self.banned_path is not None:
            raise ConfigError("banned and banned_path are mutually exclusive")
        if self.allowlist is not None and self.allowlist_path is not None:
            raise ConfigError("allowlist and allowlist_path are mutually exclusive")
        for name, path in (
            ("banned_path", self.banned_path),
            ("extra_banned_path", self.extra_banned_path),
            ("allowlist_path", self.allowlist_path),
            ("extra_allowlist_path", self.extra_allowlist_path),
        ):
            if path is not None and not str(path).strip():
                raise ConfigError(f"{name} must be a non-empty path")
        for name in (
            "enable_fuzzy",
            "word_boundaries",
            "normalize_leet",
            "normalize_separated_runs",
            "normalize_repeated_chars",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ConfigError(f"{name} must be bool")
        for name in ("threshold", "min_fuzzy_len", "fuzzy_length_delta", "fuzzy_max_token_len"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConfigError(f"{name} must be int")
        if not (0 <= self.threshold <= 100):
            raise ConfigError("threshold must be in 0..100")
        if self.min_fuzzy_len < 1:
            raise ConfigError("min_fuzzy_len must be >= 1")
        if self.fuzzy_length_delta < 0:
            raise ConfigError("fuzzy_length_delta must be >= 0")
        if self.fuzzy_length_delta > MAX_FUZZY_LENGTH_DELTA:
            raise ConfigError(f"fuzzy_length_delta must be <= {MAX_FUZZY_LENGTH_DELTA}")
        if self.fuzzy_max_token_len > MAX_FUZZY_TOKEN_LEN:
            raise ConfigError(f"fuzzy_max_token_len must be <= {MAX_FUZZY_TOKEN_LEN}")
        if self.fuzzy_max_token_len < self.min_fuzzy_len:
            raise ConfigError("fuzzy_max_token_len must be >= min_fuzzy_len")
        _validate_mask_spec(self.mask)
        if self.categories is not None:
            if isinstance(self.categories, (str, bytes, bytearray)):
                raise ConfigError("categories must be an iterable of Category values")
            try:
                categories = frozenset(Category(category) for category in self.categories)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"unknown categories: {exc}") from exc
            object.__setattr__(self, "categories", categories)
        # Snapshot one-shot iterables and reject bare strings early.
        object.__setattr__(self, "banned", _snapshot_banned(self.banned, source="banned"))
        object.__setattr__(
            self, "extra_banned", _snapshot_banned(self.extra_banned, source="extra_banned")
        )
        object.__setattr__(
            self, "allowlist", _snapshot_allowlist(self.allowlist, source="allowlist")
        )
        object.__setattr__(
            self,
            "extra_allowlist",
            _snapshot_allowlist(self.extra_allowlist, source="extra_allowlist"),
        )

    def enabled_categories(self) -> frozenset[Category]:
        """Return the concrete enabled category set."""
        if self.categories is None:
            return frozenset(Category)
        return frozenset(self.categories)

    @property
    def builtin_mask(self) -> MaskName | None:
        """Return the validated built-in mask name, or ``None`` for a callback."""
        if isinstance(self.mask, str):
            return cast(MaskName, self.mask)
        return None

    @property
    def mask_callable(self) -> MaskFn | None:
        """Return the custom mask callback when configured."""
        if callable(self.mask) and not isinstance(self.mask, str):
            return self.mask
        return None


def _require_str(text: object, *, what: str = "text") -> str:
    if not isinstance(text, str):
        raise TypeError(f"{what} must be str")
    return text


def _require_str_sequence(texts: object) -> list[str]:
    if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
        raise TypeError("texts must be a sequence of str (not a bare str)")
    out: list[str] = []
    for i, item in enumerate(texts):
        if not isinstance(item, str):
            raise TypeError(f"texts[{i}] must be str")
        out.append(item)
    return out


def _require_str_iterable(texts: object) -> Iterable[str]:
    if isinstance(texts, (str, bytes, bytearray)):
        raise TypeError("texts must be a sequence of str (not a bare str)")
    if not isinstance(texts, Iterable):
        raise TypeError("texts must be an iterable of str")
    return cast(Iterable[str], texts)


def _apply_mask_fn(mask_fn: MaskFn, text: str, matches: list[Match]) -> str:
    out = mask_fn(text, matches)
    if not isinstance(out, str):
        raise TypeError(f"custom mask must return str, got {type(out)!r}")
    return out


def _validate_chunk_size(chunk_size: int) -> None:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise ConfigError("chunk_size must be int")
    if chunk_size < 1:
        raise ConfigError("chunk_size must be >= 1")


def _validate_workers(*, parallel: bool, workers: int | None) -> None:
    if not isinstance(parallel, bool):
        raise ConfigError("parallel must be bool")
    if workers is None:
        return
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise ConfigError("workers must be int when provided")
    if workers < 1:
        raise ConfigError("workers must be >= 1 when provided")
    if not parallel:
        raise ConfigError("workers requires parallel=True")
    if workers > 256:
        raise ConfigError("workers must be <= 256")


RawMatch = tuple[int, int, str, str, int, float, str]


def _match_from_raw(text: str, item: RawMatch) -> Match:
    category_bits = int(item[4])
    cats = categories_from_bits(category_bits)
    match = Match(
        start=int(item[0]),
        end=int(item[1]),
        text=str(item[2]),
        term=str(item[3]),
        categories=cats,
        score=float(item[5]),
        kind=cast(Literal["exact", "phrase", "fuzzy"], item[6]),
    )
    if match.text != text[match.start : match.end]:
        raise RuntimeError(
            f"match span invariant violated: {match.text!r} != {text[match.start : match.end]!r}"
        )
    return match


class Filter:
    """Compiled, immutable profanity filter.

    Construct a filter once and reuse it. Construction loads and validates the
    effective lexicon and compiles the Rust matching engine.

    Args:
        config: Immutable policy configuration. ``None`` uses ``FilterConfig``
            defaults.

    Raises:
        ConfigError: If a configured lexicon cannot be loaded or validated.
        ImportError: If the native ``profanex._core`` extension is unavailable.
    """

    __slots__ = ("_config", "_engine", "_mask_fn")

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, name):
            raise AttributeError(f"{type(self).__name__} is immutable")
        object.__setattr__(self, name, value)

    def __init__(self, config: FilterConfig | None = None) -> None:
        if config is not None and not isinstance(config, FilterConfig):
            raise TypeError("config must be FilterConfig or None")
        self._config = config if config is not None else FilterConfig()
        data = load_effective_lexicon(self._config)
        self._engine = _build_engine(self._config, data)
        self._mask_fn = self._config.mask_callable

    @classmethod
    def from_defaults(cls) -> Filter:
        """Construct a filter with the packaged lexicon and default policy."""
        return cls(FilterConfig())

    @property
    def config(self) -> FilterConfig:
        """The immutable configuration snapshot used to build this filter."""
        return self._config

    def contains(self, text: str) -> bool:
        """Return whether ``text`` contains at least one accepted match.

        This is the lowest-overhead single-text detection API and may stop after
        the first accepted match.

        Args:
            text: Source text to inspect.

        Returns:
            ``True`` when the configured policy accepts a match.

        Raises:
            TypeError: If ``text`` is not a string.
        """
        return bool(self._engine.contains(_require_str(text)))

    def find(self, text: str) -> list[Match]:
        """Return ordered, non-overlapping matches in ``text``.

        Args:
            text: Source text to inspect.

        Returns:
            Matches with half-open indices into the original Python string.

        Raises:
            TypeError: If ``text`` is not a string.
        """
        text = _require_str(text)
        return [_match_from_raw(text, item) for item in self._engine.find(text)]

    def clean(self, text: str) -> str:
        """Return ``text`` with every accepted match masked.

        Args:
            text: Source text to filter.

        Returns:
            A new string transformed by the configured built-in or custom mask.

        Raises:
            TypeError: If ``text`` is not a string or a custom mask returns a non-string.
        """
        text = _require_str(text)
        if self._mask_fn is not None:
            return _apply_mask_fn(self._mask_fn, text, self.find(text))
        return str(self._engine.clean(text))

    def analyze(self, text: str) -> tuple[bool, str]:
        """Return ``(contains_profanity, cleaned_text)`` from one scan.

        Prefer this method over separate ``contains`` and ``clean`` calls
        when both results are needed.

        Args:
            text: Source text to inspect and filter.

        Returns:
            A detection flag and the corresponding cleaned text.

        Raises:
            TypeError: If ``text`` is not a string or a custom mask returns a non-string.
        """
        text = _require_str(text)
        if self._mask_fn is not None:
            matches = self.find(text)
            return bool(matches), _apply_mask_fn(self._mask_fn, text, matches)
        contains, cleaned = self._engine.analyze(text)
        return bool(contains), str(cleaned)

    def contains_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[bool]:
        """Detect profanity in a sequence while preserving input order.

        Args:
            texts: Finite sequence of strings. A bare string is rejected.
            parallel: Use the Rust worker pool when ``True``.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Returns:
            One detection flag per input string.

        Raises:
            TypeError: If ``texts`` is not a sequence of strings.
            ConfigError: If parallel or worker options are invalid.
        """
        material = _require_str_sequence(texts)
        _validate_workers(parallel=parallel, workers=workers)
        return list(self._engine.contains_many(material, parallel=parallel, workers=workers))

    def find_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[list[Match]]:
        """Find matches in a sequence while preserving input order.

        Args:
            texts: Finite sequence of strings. A bare string is rejected.
            parallel: Use the Rust worker pool when ``True``.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Returns:
            One ordered match list per input string.

        Raises:
            TypeError: If ``texts`` is not a sequence of strings.
            ConfigError: If parallel or worker options are invalid.
        """
        material = _require_str_sequence(texts)
        _validate_workers(parallel=parallel, workers=workers)
        nested = self._engine.find_many(material, parallel=parallel, workers=workers)
        return [
            [_match_from_raw(text, item) for item in row]
            for text, row in zip(material, nested, strict=True)
        ]

    def clean_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> list[str]:
        """Mask matches in a sequence while preserving input order.

        Args:
            texts: Finite sequence of strings. A bare string is rejected.
            parallel: Use the Rust worker pool when ``True``.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Returns:
            One cleaned string per input string.

        Raises:
            TypeError: If an input or custom-mask result is not a string.
            ConfigError: If worker options are invalid or a custom mask is combined
                with parallel cleaning.
        """
        material = _require_str_sequence(texts)
        _validate_workers(parallel=parallel, workers=workers)
        if self._mask_fn is not None:
            if parallel:
                raise ConfigError(
                    "custom mask callbacks cannot be used with parallel=True; "
                    "scan with find_many(..., parallel=True) and apply the callback serially"
                )
            return [
                _apply_mask_fn(self._mask_fn, text, matches)
                for text, matches in zip(
                    material, self.find_many(material, parallel=False), strict=True
                )
            ]
        return list(self._engine.clean_many(material, parallel=parallel, workers=workers))

    def analyze_many(
        self,
        texts: Sequence[str],
        *,
        parallel: bool = False,
        workers: int | None = None,
    ) -> tuple[list[bool], list[str]]:
        """Return ordered flags and cleaned texts while scanning each input once.

        Args:
            texts: Finite sequence of strings. A bare string is rejected.
            parallel: Use the Rust worker pool when ``True``.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Returns:
            Parallel lists of detection flags and cleaned strings.

        Raises:
            TypeError: If an input or custom-mask result is not a string.
            ConfigError: If parallel or worker options are invalid.
        """
        material = _require_str_sequence(texts)
        _validate_workers(parallel=parallel, workers=workers)
        if self._mask_fn is not None:
            nested = self.find_many(material, parallel=parallel, workers=workers)
            return (
                [bool(matches) for matches in nested],
                [
                    _apply_mask_fn(self._mask_fn, text, matches)
                    for text, matches in zip(material, nested, strict=True)
                ],
            )
        flags, cleaned = self._engine.analyze_many(material, parallel=parallel, workers=workers)
        return list(flags), list(cleaned)

    def iter_contains(
        self,
        texts: Iterable[str],
        *,
        chunk_size: int = 1_000,
        parallel: bool = False,
        workers: int | None = None,
    ) -> Iterator[bool]:
        """Yield detection flags from any string iterable in bounded chunks.

        Args:
            texts: Iterable of strings.
            chunk_size: Maximum inputs materialized per batch; must be positive.
            parallel: Process each chunk using the Rust worker pool.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Yields:
            Detection flags in input order.
        """
        yield from self._iter_chunked(
            _require_str_iterable(texts),
            chunk_size=chunk_size,
            parallel=parallel,
            workers=workers,
            many=self.contains_many,
        )

    def iter_find(
        self,
        texts: Iterable[str],
        *,
        chunk_size: int = 1_000,
        parallel: bool = False,
        workers: int | None = None,
    ) -> Iterator[list[Match]]:
        """Yield match lists from any string iterable in bounded chunks.

        Args:
            texts: Iterable of strings.
            chunk_size: Maximum inputs materialized per batch; must be positive.
            parallel: Process each chunk using the Rust worker pool.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Yields:
            Ordered match lists in input order.
        """
        yield from self._iter_chunked(
            _require_str_iterable(texts),
            chunk_size=chunk_size,
            parallel=parallel,
            workers=workers,
            many=self.find_many,
        )

    def iter_clean(
        self,
        texts: Iterable[str],
        *,
        chunk_size: int = 1_000,
        parallel: bool = False,
        workers: int | None = None,
    ) -> Iterator[str]:
        """Yield cleaned strings from any string iterable in bounded chunks.

        Args:
            texts: Iterable of strings.
            chunk_size: Maximum inputs materialized per batch; must be positive.
            parallel: Process each chunk using the Rust worker pool.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Yields:
            Cleaned strings in input order.
        """
        yield from self._iter_chunked(
            _require_str_iterable(texts),
            chunk_size=chunk_size,
            parallel=parallel,
            workers=workers,
            many=self.clean_many,
        )

    def iter_analyze(
        self,
        texts: Iterable[str],
        *,
        chunk_size: int = 1_000,
        parallel: bool = False,
        workers: int | None = None,
    ) -> Iterator[tuple[bool, str]]:
        """Yield detection and cleaning results from one scan per input.

        Args:
            texts: Iterable of strings.
            chunk_size: Maximum inputs materialized per batch; must be positive.
            parallel: Process each chunk using the Rust worker pool.
            workers: Explicit worker count from 1 through 256. Requires ``parallel=True``.

        Yields:
            ``(contains_profanity, cleaned_text)`` tuples in input order.
        """
        material = _require_str_iterable(texts)
        _validate_chunk_size(chunk_size)
        _validate_workers(parallel=parallel, workers=workers)
        chunk: list[str] = []
        for item in material:
            chunk.append(_require_str(item, what="iterable item"))
            if len(chunk) >= chunk_size:
                flags, cleaned = self.analyze_many(chunk, parallel=parallel, workers=workers)
                yield from zip(flags, cleaned, strict=True)
                chunk.clear()
        if chunk:
            flags, cleaned = self.analyze_many(chunk, parallel=parallel, workers=workers)
            yield from zip(flags, cleaned, strict=True)

    def _iter_chunked(
        self,
        texts: Iterable[str],
        *,
        chunk_size: int,
        parallel: bool,
        workers: int | None,
        many: Callable[..., list[_T]],
    ) -> Iterator[_T]:
        _validate_chunk_size(chunk_size)
        _validate_workers(parallel=parallel, workers=workers)
        chunk: list[str] = []
        for item in texts:
            chunk.append(_require_str(item, what="iterable item"))
            if len(chunk) >= chunk_size:
                yield from many(chunk, parallel=parallel, workers=workers)
                chunk.clear()
        if chunk:
            yield from many(chunk, parallel=parallel, workers=workers)


def _build_engine(config: FilterConfig, data: LexiconData):
    try:
        from profanex._core import Engine
    except ImportError as exc:  # pragma: no cover - packaging failure path
        raise ImportError(
            "profanex._core native extension is not built. "
            "Install a wheel or build with: maturin develop"
        ) from exc

    banned: list[dict[str, object]] = [
        {
            "term": entry.term,
            "pattern": entry.pattern,
            "categories": entry.category_bits,
        }
        for entry in data.banned
    ]
    # Built-in engine mask; callables are applied in Python after find*.
    mask = config.builtin_mask or "stars"
    try:
        return Engine(
            banned,
            list(data.allowlist),
            word_boundaries=config.word_boundaries,
            normalize_leet=config.normalize_leet,
            normalize_repeated_chars=config.normalize_repeated_chars,
            normalize_separated_runs=config.normalize_separated_runs,
            enable_fuzzy=config.enable_fuzzy,
            threshold=float(config.threshold),
            min_fuzzy_len=config.min_fuzzy_len,
            fuzzy_length_delta=config.fuzzy_length_delta,
            fuzzy_max_token_len=config.fuzzy_max_token_len,
            mask=mask,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


__all__ = [
    "Category",
    "ConfigError",
    "Filter",
    "FilterConfig",
    "Match",
]
