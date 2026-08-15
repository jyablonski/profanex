"""Mask strategy helpers (validation; hot path lives in Rust)."""

from __future__ import annotations

from typing import Literal, cast

from profanex.lexicon import ConfigError

MaskName = Literal["stars", "vowels"]

SUPPORTED_MASKS: frozenset[str] = frozenset({"stars", "vowels"})


def validate_mask(mask: str) -> MaskName:
    if mask not in SUPPORTED_MASKS:
        raise ConfigError(f"unsupported mask: {mask!r}")
    return cast(MaskName, mask)
