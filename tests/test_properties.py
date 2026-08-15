"""Property-style invariants for public Match spans and projections."""

from __future__ import annotations

import itertools

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from profanex import Filter, FilterConfig

TEXTS = [
    "",
    "a",
    "hello world",
    "what the fuck",
    "you are a b1tch!!",
    "🔥fuck🔥",
    "WHAT THE FUCK",
    "please pass the salt",
    "asshole",
    "fuck and shit",
    "a blow job here",
    "ﬁne classic",
    "これはテストです",
    "x" * 200,
]


@pytest.fixture(scope="module")
def fuzzy_filter() -> Filter:
    return Filter(FilterConfig(enable_fuzzy=True, threshold=85, min_fuzzy_len=4))


@pytest.mark.parametrize("text", TEXTS)
def test_match_text_equals_slice(default_filter: Filter, text: str) -> None:
    for m in default_filter.find(text):
        assert 0 <= m.start <= m.end <= len(text)
        assert m.text == text[m.start : m.end]


@pytest.mark.parametrize("text", TEXTS)
def test_projection_parity(default_filter: Filter, text: str) -> None:
    matches = default_filter.find(text)
    assert default_filter.contains(text) is bool(matches)
    cleaned = default_filter.clean(text)
    chars = list(text)
    for m in matches:
        for i in range(m.start, m.end):
            chars[i] = "*"
    assert cleaned == "".join(chars)


@pytest.mark.parametrize("text", TEXTS)
def test_matches_sorted_nonoverlapping(default_filter: Filter, text: str) -> None:
    matches = default_filter.find(text)
    prev_end = 0
    for m in matches:
        assert m.start >= prev_end
        prev_end = m.end


@pytest.mark.parametrize("text", TEXTS)
def test_fuzzy_preserves_span_invariant(fuzzy_filter: Filter, text: str) -> None:
    for m in fuzzy_filter.find(text):
        assert m.text == text[m.start : m.end]
        assert m.kind in {"exact", "phrase", "fuzzy"}


def test_construct_from_many_configs_deterministic() -> None:
    texts = ["fuck", "fukc", "classic", "blow job"]
    cfg = FilterConfig(
        banned=["fuck", "blow job"],
        allowlist=[],
        enable_fuzzy=True,
        threshold=75,
    )
    a = Filter(cfg)
    b = Filter(cfg)
    for text in texts:
        assert a.find(text) == b.find(text)
        assert a.clean(text) == b.clean(text)


def test_serial_parallel_property_batch() -> None:
    f = Filter(FilterConfig(banned=["fuck", "shit"], allowlist=[]))
    texts = list(
        itertools.chain.from_iterable(
            [[t, t.upper(), f"xx {t} yy"] for t in ["fuck", "shit", "clean", "pass"]]
        )
    )
    assert f.find_many(texts) == f.find_many(texts, parallel=True, workers=2)
    assert f.clean_many(texts) == f.clean_many(texts, parallel=True, workers=2)


UNICODE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=256,
)

GENERATED_FILTERS = (
    Filter(FilterConfig(banned=["fuck", "shit", "straße", "é", "οσ", "blow job"])),
    Filter(
        FilterConfig(
            banned=["fuck", "shit", "straße", "é", "οσ", "blow job"],
            allowlist=["pass"],
            normalize_repeated_chars=True,
            normalize_separated_runs=True,
        )
    ),
    Filter(
        FilterConfig(
            banned=["fuck", "shit", "straße", "é", "οσ", "blow job"],
            allowlist=["pass"],
            enable_fuzzy=True,
            threshold=75,
        )
    ),
)
DEFAULT_GENERATED_FILTER = Filter()


@settings(max_examples=300, deadline=None)
@given(text=UNICODE_TEXT)
def test_generated_unicode_public_invariants(text: str) -> None:
    for filter_ in GENERATED_FILTERS:
        matches = filter_.find(text)
        assert filter_.contains(text) is bool(matches)
        assert filter_.analyze(text) == (bool(matches), filter_.clean(text))
        previous_end = 0
        expected = list(text)
        for match in matches:
            assert previous_end <= match.start < match.end <= len(text)
            assert match.text == text[match.start : match.end]
            for index in range(match.start, match.end):
                expected[index] = "*"
            previous_end = match.end
        assert filter_.clean(text) == "".join(expected)


@settings(max_examples=200, deadline=None)
@given(token=st.text(alphabet="0123456789", min_size=1, max_size=128))
def test_generated_numeric_tokens_do_not_trigger_default_leet(token: str) -> None:
    assert DEFAULT_GENERATED_FILTER.find(token) == []


@settings(max_examples=100, deadline=None)
@given(
    token=st.sampled_from(("455", "80085")),
    non_latin=st.text(alphabet="中日字กขค", min_size=1, max_size=16),
)
def test_generated_numeric_tokens_next_to_non_latin_text_stay_clean(
    token: str, non_latin: str
) -> None:
    assert DEFAULT_GENERATED_FILTER.find(token + non_latin) == []
    assert DEFAULT_GENERATED_FILTER.find(non_latin + token) == []


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=32),
    term=st.sampled_from(
        ("fuck", "FUCK", "fuuuck", "f.u.c.k", "b1tch", "sh!t", "straße", "STRASSE", "é")
    ),
    suffix=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=32),
)
def test_generated_unicode_projection_around_known_terms(
    prefix: str, term: str, suffix: str
) -> None:
    filter_ = Filter(
        FilterConfig(
            banned=["fuck", "bitch", "shit", "straße", "é"],
            allowlist=[],
            normalize_repeated_chars=True,
            normalize_separated_runs=True,
        )
    )
    text = prefix + term + suffix
    for match in filter_.find(text):
        assert match.text == text[match.start : match.end]
