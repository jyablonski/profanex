"""Drive public API validation from fixtures/api and fixtures/corpora."""

from __future__ import annotations

import pytest
from fixtures.loader import (
    assert_match_equals,
    assert_projection_case,
    filter_from_case,
    iter_api_suites,
    iter_corpora_suites,
    load_latency_samples,
    load_suite,
)
from profanex import Filter


def _api_projection_suites() -> list[str]:
    # batch.yaml uses a different schema (texts / expect_*_many).
    return [s for s in iter_api_suites() if not s.endswith("/batch")]


@pytest.mark.parametrize("suite", _api_projection_suites())
def test_api_fixture_suite(suite: str) -> None:
    for case in load_suite(suite):
        assert_projection_case(case)


@pytest.mark.parametrize("suite", list(iter_corpora_suites()))
def test_corpora_fixture_suite(suite: str) -> None:
    for case in load_suite(suite):
        if suite.endswith("/fp"):
            f = Filter()
            text = case["text"]
            assert f.find(text) == [], case["id"]
            assert f.contains(text) is False, case["id"]
            assert f.clean(text) == text, case["id"]
        else:
            assert_projection_case(case)


@pytest.mark.parametrize("case", load_suite("api/batch"), ids=lambda c: c["id"])
def test_batch_fixtures(case: dict) -> None:
    f = filter_from_case(case)
    texts = list(case["texts"])

    if "expect_contains_many" in case:
        assert f.contains_many(texts) == case["expect_contains_many"], case["id"]
    if "expect_find_many" in case:
        got = f.find_many(texts)
        expected = case["expect_find_many"]
        assert len(got) == len(expected), case["id"]
        for row_got, row_exp in zip(got, expected, strict=True):
            assert len(row_got) == len(row_exp), case["id"]
            for g, e in zip(row_got, row_exp, strict=True):
                assert_match_equals(g, e, case_id=case["id"])
    if "expect_clean_many" in case:
        assert f.clean_many(texts) == case["expect_clean_many"], case["id"]
    if case.get("expect_parallel_equals_serial"):
        assert f.contains_many(texts) == f.contains_many(texts, parallel=True, workers=2), case[
            "id"
        ]
        assert f.find_many(texts) == f.find_many(texts, parallel=True, workers=2), case["id"]
        assert f.clean_many(texts) == f.clean_many(texts, parallel=True, workers=2), case["id"]


def test_latency_samples_have_stable_tags() -> None:
    samples = load_latency_samples()
    assert len(samples) >= 8
    ids = {s.id for s in samples}
    assert {"clean_prose", "exact_fuck", "fuzzy_typo", "long_dense"} <= ids
    for sample in samples:
        if sample.expect_contains is None:
            continue
        f = Filter()
        # fuzzy_typo is expected false under default (fuzzy off)
        assert f.contains(sample.text) is sample.expect_contains, sample.id


def test_fixture_inventory_minimums() -> None:
    assert len(load_suite("corpora/fp")) >= 16
    assert len(load_suite("corpora/tp")) >= 10
    assert len(load_suite("corpora/defaults_out_of_box")) >= 40
    assert len(load_suite("api/config_errors")) >= 8
    assert len(list(iter_api_suites())) >= 5
    assert len(list(iter_corpora_suites())) >= 6
