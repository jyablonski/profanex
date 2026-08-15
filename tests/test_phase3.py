from __future__ import annotations

from profanex import Filter, FilterConfig


def test_repeated_chars_optional() -> None:
    off = Filter(FilterConfig(banned=["fuck"], allowlist=[]))
    on = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            normalize_repeated_chars=True,
        )
    )
    assert off.contains("fuuuck") is False
    assert on.contains("fuuuck") is True
    m = on.find("fuuuck")[0]
    assert m.text == "fuuuck"
    assert m.term == "fuck"
    assert on.clean("fuuuck") == "******"


def test_separated_runs_optional() -> None:
    off = Filter(FilterConfig(banned=["fuck"], allowlist=[]))
    on = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            normalize_separated_runs=True,
        )
    )
    assert off.contains("f.u.c.k") is False
    assert on.contains("f.u.c.k") is True
    m = on.find("say f.u.c.k now")[0]
    assert m.text == "f.u.c.k"
    assert m.term == "fuck"


def test_separated_runs_fp_safe_for_prose() -> None:
    f = Filter(
        FilterConfig(
            banned=["ass"],
            allowlist=[],
            normalize_separated_runs=True,
        )
    )
    assert f.contains("hello.world") is False
    assert f.contains("a.b") is False


def test_fuzzy_typo_and_projection_parity() -> None:
    f = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            enable_fuzzy=True,
            threshold=75,
            min_fuzzy_len=4,
        )
    )
    text = "what the fukc"
    assert f.contains(text) is True
    matches = f.find(text)
    assert len(matches) == 1
    assert matches[0].kind == "fuzzy"
    assert matches[0].term == "fuck"
    assert matches[0].text == text[matches[0].start : matches[0].end] == "fukc"
    assert f.contains(text) == bool(matches)
    assert f.clean(text) == "what the ****"


def test_fuzzy_off_by_default() -> None:
    f = Filter(FilterConfig(banned=["fuck"], allowlist=[]))
    assert f.contains("fukc") is False


def test_fuzzy_min_len_excludes_short_stems() -> None:
    f = Filter(
        FilterConfig(
            banned=["ass", "fuck"],
            allowlist=[],
            enable_fuzzy=True,
            threshold=50,
            min_fuzzy_len=4,
        )
    )
    # short stem is exact-only; typo should not fuzzy-match
    assert f.contains("asx") is False
    assert f.contains("ass") is True  # exact still works


def test_fuzzy_fp_defaults_still_clean() -> None:
    # Default packaged filter with fuzzy on should not flag FP magnets via fuzzy.
    f = Filter(FilterConfig(enable_fuzzy=True, threshold=85, min_fuzzy_len=4))
    for text in [
        "please pass the salt",
        "bass guitar",
        "classic literature",
        "a bad assumption",
        "press the button",
    ]:
        assert f.find(text) == [], text


def test_fuzzy_deterministic_ties() -> None:
    f = Filter(
        FilterConfig(
            banned=["abcd", "abce"],
            allowlist=[],
            enable_fuzzy=True,
            threshold=70,
            min_fuzzy_len=4,
        )
    )
    a = f.find("abcf")
    b = f.find("abcf")
    assert a == b
    assert len(a) == 1


def test_adversarial_long_token_bounded() -> None:
    f = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            enable_fuzzy=True,
            threshold=80,
            fuzzy_max_token_len=64,
        )
    )
    huge = "x" * 10_000
    assert f.contains(huge) is False
    assert f.find(huge) == []


def test_adversarial_large_lexicon_completes() -> None:
    banned = [f"word{i:04d}" for i in range(2_000)] + ["target"]
    f = Filter(
        FilterConfig(
            banned=banned,
            allowlist=[],
            enable_fuzzy=True,
            threshold=90,
            min_fuzzy_len=4,
        )
    )
    assert f.contains("targat") is True or f.contains("target") is True
    # ensure call returns promptly with a near-miss token
    assert isinstance(f.find("zzzz"), list)


def test_combined_obfuscation_and_fuzzy() -> None:
    f = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            normalize_repeated_chars=True,
            normalize_separated_runs=True,
            enable_fuzzy=True,
            threshold=80,
        )
    )
    assert f.contains("f.u.u.u.c.k") is True  # join then squash → fuck
    assert f.contains("fuuuck") is True
