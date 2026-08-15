"""Config validation and lexicon loading edge cases (coverage)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from profanex import Category, ConfigError, Filter, FilterConfig
from profanex.lexicon import (
    BannedEntry,
    categories_from_bits,
    category_bits,
    load_effective_lexicon,
)
from profanex.masks import validate_mask


def test_callable_mask_must_return_str() -> None:
    def bad(_text: str, _matches: object) -> object:
        return 42

    f = Filter(FilterConfig(banned=["fuck"], allowlist=[], mask=bad))  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="custom mask must return str"):
        f.clean("fuck")


def test_category_mapping_accepts_tuple_sequence() -> None:
    f = Filter(
        FilterConfig(
            banned={"general": ("secret",)},
            allowlist=[],
        )
    )
    assert f.contains("secret")


def test_category_mapping_accepts_category_enum_keys() -> None:
    f = Filter(
        FilterConfig(
            banned={Category.GENERAL: ["secret"]},
            allowlist=[],
        )
    )
    assert f.contains("secret")


def test_empty_lexicon_paths_rejected() -> None:
    with pytest.raises(ConfigError, match="banned_path must be a non-empty path"):
        FilterConfig(banned_path="  ")
    with pytest.raises(ConfigError, match="allowlist_path must be a non-empty path"):
        FilterConfig(allowlist_path="")


def test_from_defaults_and_config_property() -> None:
    f = Filter.from_defaults()
    assert f.config.threshold == 85
    assert f.contains("fuck") is True


def test_config_snapshots_categories_and_filter_is_immutable() -> None:
    categories: set[Category] = set()
    cfg = FilterConfig(
        categories=categories,  # ty: ignore[invalid-argument-type]
        banned=["secret"],
        allowlist=[],
    )
    categories.add(Category.GENERAL)
    assert cfg.enabled_categories() == frozenset()

    f = Filter(cfg)
    with pytest.raises(AttributeError, match="immutable"):
        f._config = FilterConfig()


def test_normalized_allowlist_override_uses_engine_casefold() -> None:
    f = Filter(FilterConfig(banned=["straße"], allowlist=["STRASSE"]))
    assert f.contains("Straße") is False
    assert f.find("STRASSE") == []


def test_extra_allowlist_can_disable_packaged_exact_term() -> None:
    f = Filter(FilterConfig(extra_allowlist=["fuck"]))
    assert f.contains("fuck") is False


def test_filter_config_mutual_exclusion(tmp_path: Path) -> None:
    path = tmp_path / "banned.yaml"
    path.write_text("- alpha\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="banned and banned_path"):
        FilterConfig(banned=["x"], banned_path=str(path))
    with pytest.raises(ConfigError, match="allowlist and allowlist_path"):
        FilterConfig(allowlist=[], allowlist_path=str(tmp_path / "a.yaml"))


def test_filter_config_numeric_and_mask_validation() -> None:
    with pytest.raises(ConfigError, match="threshold"):
        FilterConfig(threshold=-1)
    with pytest.raises(ConfigError, match="threshold"):
        FilterConfig(threshold=101)
    with pytest.raises(ConfigError, match="min_fuzzy_len"):
        FilterConfig(min_fuzzy_len=0)
    with pytest.raises(ConfigError, match="fuzzy_length_delta"):
        FilterConfig(fuzzy_length_delta=-1)
    with pytest.raises(ConfigError, match="fuzzy_length_delta"):
        FilterConfig(fuzzy_length_delta=65)
    with pytest.raises(ConfigError, match="fuzzy_max_token_len"):
        FilterConfig(min_fuzzy_len=8, fuzzy_max_token_len=4)
    with pytest.raises(ConfigError, match="fuzzy_max_token_len"):
        FilterConfig(fuzzy_max_token_len=257)
    with pytest.raises(ConfigError, match="mask must be"):
        FilterConfig(mask=123)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ConfigError, match="unsupported mask"):
        validate_mask("garbage")
    with pytest.raises(ConfigError, match="unknown categories"):
        FilterConfig(categories=frozenset({"nope"}))  # ty: ignore[invalid-argument-type]
    with pytest.raises(ConfigError, match="threshold must be int"):
        FilterConfig(threshold=True)
    with pytest.raises(ConfigError, match="enable_fuzzy must be bool"):
        FilterConfig(enable_fuzzy=1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ConfigError, match="terms in banned must be str"):
        FilterConfig(banned=[123])  # ty: ignore[invalid-argument-type]


def test_callable_mask_accepted() -> None:
    def redact(text: str, matches: object) -> str:
        if not matches:
            return text
        return "alpha [x]"

    cfg = FilterConfig(banned=["beta"], allowlist=[], mask=redact)
    assert cfg.builtin_mask is None
    assert cfg.mask_callable is redact
    f = Filter(cfg)
    assert f.clean("alpha beta") == "alpha [x]"


def test_type_errors_on_api() -> None:
    f = Filter(FilterConfig(banned=["beta"], allowlist=[]))
    with pytest.raises(TypeError, match="text must be str"):
        f.contains(123)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="sequence of str"):
        f.contains_many("beta")
    with pytest.raises(TypeError, match=r"texts\[0\] must be str"):
        f.contains_many([123])  # ty: ignore[invalid-argument-type]
    for invalid_config in (False, 0, "", {}, []):
        with pytest.raises(TypeError, match="config must be FilterConfig or None"):
            Filter(invalid_config)  # ty: ignore[invalid-argument-type]


def test_banned_path_and_extra_paths(tmp_path: Path) -> None:
    banned = tmp_path / "banned.yaml"
    banned.write_text(
        yaml.dump({"general": ["alpha"], "sexual": ["beta"]}),
        encoding="utf-8",
    )
    extra = tmp_path / "extra.yaml"
    extra.write_text("- gamma\n", encoding="utf-8")
    allow = tmp_path / "allow.yaml"
    allow.write_text("- safe\n", encoding="utf-8")
    extra_allow = tmp_path / "extra_allow.yaml"
    extra_allow.write_text(
        yaml.dump({"general": ["okword"]}),
        encoding="utf-8",
    )

    f = Filter(
        FilterConfig(
            banned_path=str(banned),
            extra_banned_path=str(extra),
            allowlist_path=str(allow),
            extra_allowlist_path=str(extra_allow),
        )
    )
    assert f.contains("alpha")
    assert f.contains("gamma")
    assert f.contains("safe") is False
    assert f.contains("okword") is False


def test_extra_banned_mapping_and_category_filter() -> None:
    data = load_effective_lexicon(
        FilterConfig(
            banned=["keep"],
            allowlist=[],
            categories=frozenset({Category.GENERAL}),
            extra_banned={"general": ["also"], "slurs": ["ignored"]},
        )
    )
    terms = {e.term for e in data.banned}
    assert terms == {"also", "keep"}
    assert category_bits([Category.GENERAL, Category.SEXUAL]) == (1 << 0) | (1 << 1)
    assert categories_from_bits((1 << 0) | (1 << 1)) == frozenset(
        {Category.GENERAL, Category.SEXUAL}
    )
    with pytest.raises(RuntimeError, match="unknown category bits"):
        categories_from_bits(1 << 31)
    entry = BannedEntry(term="x", pattern="x", categories=frozenset({Category.GENERAL}))
    assert entry.category_bits == 1


def test_flat_custom_terms_remain_enabled_without_general_category() -> None:
    f = Filter(
        FilterConfig(
            categories=frozenset({Category.SEXUAL}),
            banned=["customterm"],
            allowlist=[],
            extra_banned=["anotherterm"],
        )
    )
    assert f.contains("customterm and anotherterm")
    assert all(match.categories == frozenset({Category.SEXUAL}) for match in f.find("customterm"))


def test_lexicon_parse_errors(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(ConfigError, match="not found"):
        Filter(FilterConfig(banned_path=str(missing)))

    huge = tmp_path / "huge.yaml"
    huge.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    with pytest.raises(ConfigError, match="too large"):
        Filter(FilterConfig(banned_path=str(huge)))

    bad_cat = tmp_path / "bad_cat.yaml"
    bad_cat.write_text(yaml.dump({"not_a_category": ["x"]}), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown category"):
        Filter(FilterConfig(banned_path=str(bad_cat), allowlist=[]))

    bad_list = tmp_path / "bad_list.yaml"
    bad_list.write_text(yaml.dump({"general": "not-a-list"}), encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a sequence"):
        Filter(FilterConfig(banned_path=str(bad_list), allowlist=[]))

    bad_shape = tmp_path / "bad_shape.yaml"
    bad_shape.write_text("42\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a list or category mapping"):
        Filter(FilterConfig(banned_path=str(bad_shape), allowlist=[]))

    with pytest.raises(ConfigError, match="invalid term"):
        Filter(FilterConfig(banned=["  "], allowlist=[]))

    bad_allow = tmp_path / "bad_allow.yaml"
    bad_allow.write_text("not-a-list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="allowlist .* must be a list or mapping"):
        Filter(FilterConfig(banned=["z"], allowlist_path=str(bad_allow)))

    bad_allow_cat = tmp_path / "bad_allow_cat.yaml"
    bad_allow_cat.write_text(yaml.dump({"general": "nope"}), encoding="utf-8")
    with pytest.raises(ConfigError, match="allowlist categories .* must be sequences"):
        Filter(FilterConfig(banned=["z"], allowlist_path=str(bad_allow_cat)))


def test_rejects_bare_string_lexicon_containers() -> None:
    with pytest.raises(ConfigError, match="bare string"):
        Filter(FilterConfig(banned="ab", allowlist=[]))
    with pytest.raises(ConfigError, match="bare string"):
        Filter(FilterConfig(banned=["x"], allowlist="pass"))
    with pytest.raises(ConfigError, match="bare string"):
        Filter(FilterConfig(banned=["x"], allowlist=[], extra_allowlist="y"))
    with pytest.raises(ConfigError, match="sequence of terms"):
        Filter(FilterConfig(banned=["x"], allowlist={"pass": ["x"]}))


def test_empty_yaml_lexicon_files(tmp_path: Path) -> None:
    empty_banned = tmp_path / "empty_banned.yaml"
    empty_banned.write_text("", encoding="utf-8")
    empty_allow = tmp_path / "empty_allow.yaml"
    empty_allow.write_text("", encoding="utf-8")
    f = Filter(
        FilterConfig(
            banned_path=str(empty_banned),
            allowlist_path=str(empty_allow),
            extra_banned=["secret"],
            extra_allowlist=["keep"],
        )
    )
    assert f.contains("secret")
    assert f.contains("keep") is False
