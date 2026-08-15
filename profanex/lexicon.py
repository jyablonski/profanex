"""Lexicon loading, category metadata, and merge precedence."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from profanex.api import FilterConfig


class ConfigError(ValueError):
    """Invalid filter configuration or lexicon input."""


class Category(str, Enum):
    """Built-in moderation-policy category."""

    GENERAL = "general"
    SEXUAL = "sexual"
    EXCRETORY = "excretory"
    SLURS = "slurs"
    VIOLENCE = "violence"


# Must stay aligned with profanex_core::category bitflags.
_CATEGORY_BITS: dict[Category, int] = {
    Category.GENERAL: 1 << 0,
    Category.SEXUAL: 1 << 1,
    Category.EXCRETORY: 1 << 2,
    Category.SLURS: 1 << 3,
    Category.VIOLENCE: 1 << 4,
}


def category_bits(categories: Iterable[Category]) -> int:
    bits = 0
    for cat in categories:
        bits |= _CATEGORY_BITS[Category(cat)]
    return bits


def categories_from_bits(bits: int) -> frozenset[Category]:
    known_bits = sum(_CATEGORY_BITS.values())
    if bits & ~known_bits:
        raise RuntimeError(f"engine returned unknown category bits: {bits:#x}")
    return frozenset(category for category, bit in _CATEGORY_BITS.items() if bits & bit)


@dataclass(frozen=True, slots=True)
class BannedEntry:
    term: str
    pattern: str
    categories: frozenset[Category]

    @property
    def category_bits(self) -> int:
        return category_bits(self.categories)


@dataclass(frozen=True, slots=True)
class LexiconData:
    banned: tuple[BannedEntry, ...]
    allowlist: tuple[str, ...]


def _read_yaml_file(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"lexicon file not found: {path}")
    size = path.stat().st_size
    if size > 10 * 1024 * 1024:
        raise ConfigError(f"lexicon file too large: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _package_data_text(name: str) -> str:
    root = resources.files("profanex.data")
    target = root.joinpath(name)
    if not target.is_file():
        raise ConfigError(f"packaged lexicon missing: {name}")
    return target.read_text(encoding="utf-8")


def _require_term(item: object, *, source: str) -> str:
    if not isinstance(item, str) or not item.strip():
        raise ConfigError(f"invalid term in {source}: {item!r}")
    return item.strip()


def _reject_bare_string(data: object, *, source: str, what: str) -> None:
    """Bare str/bytes iterate as characters; that is never a valid lexicon container."""
    if isinstance(data, (str, bytes, bytearray)):
        raise ConfigError(f"{what} in {source} must be a list or mapping, not a bare string")


def _parse_banned_mapping(
    data: object,
    *,
    source: str,
    flat_categories: frozenset[Category] = frozenset({Category.GENERAL}),
) -> dict[str, set[Category]]:
    """Return canonical term → categories."""
    out: dict[str, set[Category]] = {}
    if data is None:
        return out
    _reject_bare_string(data, source=source, what="banned lexicon")
    if isinstance(data, list):
        for item in data:
            term = _require_term(item, source=source)
            out.setdefault(term, set()).update(flat_categories)
        return out
    if isinstance(data, dict):
        for key, words in data.items():
            try:
                cat = Category(str(key))
            except ValueError as exc:
                raise ConfigError(f"unknown category {key!r} in {source}") from exc
            if isinstance(words, (str, bytes, bytearray)) or not isinstance(words, Sequence):
                raise ConfigError(f"category {key!r} in {source} must be a sequence of terms")
            for item in words:
                term = _require_term(item, source=source)
                out.setdefault(term, set()).add(cat)
        return out
    raise ConfigError(f"banned lexicon in {source} must be a list or category mapping")


def _parse_allowlist(data: object, *, source: str) -> set[str]:
    if data is None:
        return set()
    _reject_bare_string(data, source=source, what="allowlist")
    if isinstance(data, list):
        words: list[object] = list(data)
    elif isinstance(data, dict):
        words = []
        for key, value in data.items():
            try:
                Category(str(key))
            except ValueError as exc:
                raise ConfigError(f"unknown category {key!r} in {source}") from exc
            if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
                raise ConfigError(f"allowlist categories in {source} must be sequences")
            words.extend(value)
    else:
        raise ConfigError(f"allowlist in {source} must be a list or mapping")
    return {_require_term(item, source=source) for item in words}


def _collection_to_banned(
    data: Collection[str] | Mapping[str, Collection[str]],
    *,
    source: str,
    flat_categories: frozenset[Category],
) -> dict[str, set[Category]]:
    _reject_bare_string(data, source=source, what="banned lexicon")
    if isinstance(data, Mapping):
        return _parse_banned_mapping(dict(data), source=source, flat_categories=flat_categories)
    return _parse_banned_mapping(  # type: ignore[arg-type]
        list(data), source=source, flat_categories=flat_categories
    )


def _collection_to_allowlist(data: Collection[str], *, source: str) -> set[str]:
    _reject_bare_string(data, source=source, what="allowlist")
    if isinstance(data, Mapping):
        raise ConfigError(
            f"allowlist in {source} must be a sequence of terms, not a mapping; "
            "use allowlist_path / YAML for category-shaped allowlists"
        )
    return {_require_term(x, source=source) for x in data}


def _merge_extra(
    filtered: dict[str, set[Category]],
    extra: dict[str, set[Category]],
    categories: frozenset[Category],
) -> None:
    for term, cats in extra.items():
        kept = {c for c in cats if c in categories}
        if kept:
            filtered.setdefault(term, set()).update(kept)


def _load_banned_base(
    config: FilterConfig, *, flat_categories: frozenset[Category]
) -> dict[str, set[Category]]:
    if config.banned is not None:
        return _collection_to_banned(
            config.banned, source="banned", flat_categories=flat_categories
        )
    if config.banned_path is not None:
        raw = _read_yaml_file(Path(config.banned_path))
        return _parse_banned_mapping(
            raw, source=str(config.banned_path), flat_categories=flat_categories
        )
    return _parse_banned_mapping(
        yaml.safe_load(_package_data_text("banned_words.yaml")),
        source="package:banned_words.yaml",
    )


def _load_allowlist_base(config: FilterConfig) -> set[str]:
    if config.allowlist is not None:
        return _collection_to_allowlist(config.allowlist, source="allowlist")
    if config.allowlist_path is not None:
        raw = _read_yaml_file(Path(config.allowlist_path))
        return _parse_allowlist(raw, source=str(config.allowlist_path))
    return _parse_allowlist(
        yaml.safe_load(_package_data_text("allowlist.yaml")),
        source="package:allowlist.yaml",
    )


def load_effective_lexicon(config: FilterConfig) -> LexiconData:
    """Apply replacement → category filter → extras → allowlist precedence.

    The Rust compiler is the single normalization authority. Normalized allowlist
    spans take final precedence over banned candidates.
    """
    categories = config.enabled_categories()
    # Flat custom lexicons have no category metadata. Preserve the historical
    # GENERAL assignment when it is enabled; otherwise assign the selected
    # categories so a flat custom term is not silently discarded.
    flat_categories = (
        frozenset({Category.GENERAL}) if Category.GENERAL in categories else categories
    )
    banned_map = _load_banned_base(config, flat_categories=flat_categories)

    filtered: dict[str, set[Category]] = {}
    for term, cats in banned_map.items():
        kept = {c for c in cats if c in categories}
        if kept:
            filtered[term] = kept

    if config.extra_banned is not None:
        _merge_extra(
            filtered,
            _collection_to_banned(
                config.extra_banned,
                source="extra_banned",
                flat_categories=flat_categories,
            ),
            categories,
        )
    if config.extra_banned_path is not None:
        raw = _read_yaml_file(Path(config.extra_banned_path))
        _merge_extra(
            filtered,
            _parse_banned_mapping(
                raw,
                source=str(config.extra_banned_path),
                flat_categories=flat_categories,
            ),
            categories,
        )

    allow = _load_allowlist_base(config)
    if config.extra_allowlist is not None:
        allow |= _collection_to_allowlist(config.extra_allowlist, source="extra_allowlist")
    if config.extra_allowlist_path is not None:
        raw = _read_yaml_file(Path(config.extra_allowlist_path))
        allow |= _parse_allowlist(raw, source=str(config.extra_allowlist_path))

    entries = tuple(
        BannedEntry(term=term, pattern=term, categories=frozenset(cats))
        for term, cats in sorted(filtered.items(), key=lambda kv: kv[0].casefold())
    )
    return LexiconData(
        banned=entries,
        allowlist=tuple(sorted(allow, key=str.casefold)),
    )
