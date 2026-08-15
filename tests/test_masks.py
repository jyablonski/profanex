"""Lightweight mask helpers."""

from __future__ import annotations

import pytest
from profanex.masks import SUPPORTED_MASKS, validate_mask


def test_validate_mask_accepts_supported() -> None:
    assert validate_mask("stars") == "stars"
    assert validate_mask("vowels") == "vowels"
    assert "stars" in SUPPORTED_MASKS


def test_validate_mask_rejects_unknown() -> None:
    from profanex.lexicon import ConfigError

    with pytest.raises(ConfigError, match="unsupported mask"):
        validate_mask("redact")
