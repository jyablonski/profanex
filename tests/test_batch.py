from __future__ import annotations

import pytest
from profanex import ConfigError, Filter, FilterConfig, Match


@pytest.fixture(scope="module")
def batch_filter() -> Filter:
    return Filter(
        FilterConfig(
            banned=["fuck", "shit", "ass"],
            allowlist=[],
        )
    )


def _corpus(n: int = 40) -> list[str]:
    out: list[str] = []
    for i in range(n):
        if i % 4 == 0:
            out.append(f"row {i} has fuck in it")
        elif i % 4 == 1:
            out.append(f"clean prose {i}")
        elif i % 4 == 2:
            out.append(f"some shit {i}")
        else:
            out.append(f"classic pass {i}")  # boundaries: no match for ass
    return out


def test_many_empty(batch_filter: Filter) -> None:
    assert batch_filter.contains_many([]) == []
    assert batch_filter.find_many([]) == []
    assert batch_filter.clean_many([]) == []
    assert batch_filter.analyze_many([]) == ([], [])


def test_many_order_preserved(batch_filter: Filter) -> None:
    texts = _corpus()
    flags = batch_filter.contains_many(texts)
    assert len(flags) == len(texts)
    assert flags == [batch_filter.contains(t) for t in texts]

    found = batch_filter.find_many(texts)
    assert [bool(row) for row in found] == flags
    for text, row in zip(texts, found, strict=True):
        assert row == batch_filter.find(text)

    cleaned = batch_filter.clean_many(texts)
    assert cleaned == [batch_filter.clean(t) for t in texts]


def test_serial_equals_parallel(batch_filter: Filter) -> None:
    texts = _corpus(80)
    assert batch_filter.contains_many(texts) == batch_filter.contains_many(
        texts, parallel=True, workers=2
    )
    assert batch_filter.find_many(texts) == batch_filter.find_many(texts, parallel=True, workers=2)
    assert batch_filter.clean_many(texts) == batch_filter.clean_many(
        texts, parallel=True, workers=2
    )
    assert batch_filter.analyze_many(texts) == batch_filter.analyze_many(
        texts, parallel=True, workers=2
    )


def test_analyze_scans_to_consistent_outputs(batch_filter: Filter) -> None:
    texts = ["clean", "fuck", "shit happens"]
    flags, cleaned = batch_filter.analyze_many(texts)
    assert flags == batch_filter.contains_many(texts)
    assert cleaned == batch_filter.clean_many(texts)
    assert batch_filter.analyze("fuck") == (True, "****")
    assert list(batch_filter.iter_analyze(texts, chunk_size=2)) == list(
        zip(flags, cleaned, strict=True)
    )


def test_workers_validation(batch_filter: Filter) -> None:
    with pytest.raises(ConfigError, match="workers must be >= 1"):
        batch_filter.contains_many(["a"], parallel=True, workers=0)
    with pytest.raises(ConfigError, match="workers requires parallel"):
        batch_filter.contains_many(["a"], parallel=False, workers=2)
    with pytest.raises(ConfigError, match="workers must be <= 256"):
        batch_filter.contains_many(["a"], parallel=True, workers=257)
    with pytest.raises(ConfigError, match="workers must be int"):
        batch_filter.contains_many(["a"], parallel=True, workers=1.5)  # ty: ignore[invalid-argument-type]


def test_rejects_bare_str(batch_filter: Filter) -> None:
    with pytest.raises(TypeError, match="sequence"):
        batch_filter.contains_many("not-a-sequence")
    with pytest.raises(TypeError, match="bare str"):
        list(batch_filter.iter_contains("abc"))
    with pytest.raises(TypeError, match="bare str"):
        list(batch_filter.iter_find("abc"))
    with pytest.raises(TypeError, match="bare str"):
        list(batch_filter.iter_clean("abc"))


def test_iter_clean_chunks(batch_filter: Filter) -> None:
    texts = _corpus(25)
    got = list(batch_filter.iter_clean(texts, chunk_size=7))
    assert got == batch_filter.clean_many(texts)
    assert list(batch_filter.iter_contains(texts, chunk_size=5)) == batch_filter.contains_many(
        texts
    )
    assert list(batch_filter.iter_find(texts, chunk_size=5)) == batch_filter.find_many(texts)


def test_iter_chunk_size_validation(batch_filter: Filter) -> None:
    with pytest.raises(ConfigError, match="chunk_size"):
        list(batch_filter.iter_clean(["a"], chunk_size=0))


def test_iter_parallel_matches_serial(batch_filter: Filter) -> None:
    texts = _corpus(30)
    assert list(
        batch_filter.iter_clean(texts, chunk_size=8, parallel=True, workers=2)
    ) == batch_filter.clean_many(texts)


def test_custom_mask_serial() -> None:
    def bracket(text: str, matches: list[Match]) -> str:
        if not matches:
            return text
        # simplistic: wrap first match
        m = matches[0]
        return f"{text[: m.start]}[{m.text}]{text[m.end :]}"

    f = Filter(FilterConfig(banned=["fuck"], allowlist=[], mask=bracket))
    assert f.clean("what the fuck") == "what the [fuck]"
    assert f.clean_many(["a", "fuck"]) == ["a", "[fuck]"]


def test_custom_mask_rejects_parallel() -> None:
    f = Filter(
        FilterConfig(
            banned=["fuck"],
            allowlist=[],
            mask=lambda text, _matches: text,
        )
    )
    with pytest.raises(ConfigError, match="parallel"):
        f.clean_many(["fuck"], parallel=True)
