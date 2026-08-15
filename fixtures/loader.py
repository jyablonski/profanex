"""Shared fixture loading for API contract tests and benchmarks.

Canonical data lives under ``fixtures/`` at the repo root.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from profanex import ConfigError, Filter, FilterConfig, Match

FIXTURES_ROOT = Path(__file__).resolve().parent
API_ROOT = FIXTURES_ROOT / "api"
CORPORA_ROOT = FIXTURES_ROOT / "corpora"
PERF_ROOT = FIXTURES_ROOT / "perf"

_LIST_CONFIG_KEYS = (
    "banned",
    "allowlist",
    "extra_banned",
    "extra_allowlist",
)


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"fixture root must be a mapping: {path}")
    return data


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = load_yaml(path).get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"fixture missing cases list: {path}")
    for case in cases:
        if "id" not in case:
            raise ValueError(f"case missing id in {path}: {case!r}")
    return cases


def load_suite(suite: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    """Load ``{root}/{suite}.yaml`` cases (``suite`` may include a subdirectory)."""
    base = root or FIXTURES_ROOT
    path = base / f"{suite}.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_cases(path)


def iter_api_suites() -> Iterable[str]:
    for path in sorted(API_ROOT.glob("*.yaml")):
        yield f"api/{path.stem}"


def iter_corpora_suites() -> Iterable[str]:
    for path in sorted(CORPORA_ROOT.glob("*.yaml")):
        yield f"corpora/{path.stem}"


def normalize_config_kwargs(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    kwargs = dict(raw)
    if "categories" in kwargs and kwargs["categories"] is not None:
        # Keep raw strings/enums; FilterConfig validates unknown values.
        kwargs["categories"] = frozenset(kwargs["categories"])
    for key in _LIST_CONFIG_KEYS:
        if key not in kwargs or kwargs[key] is None:
            continue
        value = kwargs[key]
        # Leave bare strings alone so lexicon loading can reject them.
        if isinstance(value, (str, bytes, bytearray)):
            continue
        if isinstance(value, dict):
            continue
        kwargs[key] = list(value)
    return kwargs


def filter_from_case(case: Mapping[str, Any]) -> Filter:
    """Build a Filter from optional ``case['config']`` (defaults when absent)."""
    return Filter(FilterConfig(**normalize_config_kwargs(case.get("config"))))


def try_filter_from_case(case: Mapping[str, Any]) -> Filter | ConfigError:
    """Like ``filter_from_case``, but returns ConfigError instead of raising."""
    try:
        return filter_from_case(case)
    except ConfigError as exc:
        return exc


def expected_matches(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    if "expect_matches" in case:
        return list(case["expect_matches"] or [])
    if "expect" in case:
        return list(case["expect"] or [])
    return []


def assert_match_equals(got: Match, expected: Mapping[str, Any], *, case_id: str) -> None:
    assert got.start == expected["start"], case_id
    assert got.end == expected["end"], case_id
    assert got.text == expected["text"], case_id
    assert got.term == expected["term"], case_id
    assert got.kind == expected["kind"], case_id
    if "score" in expected:
        assert got.score == expected["score"], case_id
    if "categories" in expected:
        assert {c.value for c in got.categories} == set(expected["categories"]), case_id


def assert_projection_case(
    case: Mapping[str, Any],
    *,
    filter_: Filter | None = None,
    check_clean_stars: bool = True,
) -> Filter:
    """Validate contains/find(/clean) against a contract or corpus case."""
    if "expect_error" in case:
        result = try_filter_from_case(case)
        assert isinstance(result, ConfigError), case["id"]
        assert case["expect_error"] in str(result), case["id"]
        return Filter()  # unused

    f = filter_ or filter_from_case(case)
    text = case["text"]
    got = f.find(text)
    expected = expected_matches(case)
    has_span_expect = "expect" in case or "expect_matches" in case

    if "expect_contains" in case:
        assert f.contains(text) is case["expect_contains"], case["id"]
    else:
        assert f.contains(text) is bool(got), case["id"]

    if has_span_expect:
        assert len(got) == len(expected), f"{case['id']}: {got!r} != {expected!r}"
        threshold = float((case.get("config") or {}).get("threshold", 85))
        for g, e in zip(got, expected, strict=True):
            assert g.text == text[g.start : g.end], case["id"]
            assert_match_equals(g, e, case_id=case["id"])
            if "score" not in e and e.get("kind") == "fuzzy":
                assert g.score >= threshold, case["id"]
    elif "expect_terms" in case:
        terms = {m.term for m in got}
        missing = set(case["expect_terms"]) - terms
        assert not missing, f"{case['id']}: missing terms {missing}; got {sorted(terms)}"
        if case.get("expect_contains", bool(case["expect_terms"])):
            assert got, case["id"]
        else:
            assert not got, case["id"]
    elif "expect_contains" in case:
        if case["expect_contains"]:
            assert got, f"{case['id']}: expected a match"
        else:
            assert not got, f"{case['id']}: unexpected {got!r}"
    else:
        assert len(got) == len(expected), f"{case['id']}: {got!r} != {expected!r}"
        threshold = float((case.get("config") or {}).get("threshold", 85))
        for g, e in zip(got, expected, strict=True):
            assert g.text == text[g.start : g.end], case["id"]
            assert_match_equals(g, e, case_id=case["id"])
            if "score" not in e and e.get("kind") == "fuzzy":
                assert g.score >= threshold, case["id"]

    if check_clean_stars and "expect_clean_stars" in case:
        assert f.clean(text) == case["expect_clean_stars"], case["id"]
    if "expect_clean_vowels" in case:
        cfg = FilterConfig(**normalize_config_kwargs(case.get("config")))
        vowels = Filter(
            FilterConfig(
                categories=cfg.categories,
                banned=cfg.banned,
                banned_path=cfg.banned_path,
                extra_banned=cfg.extra_banned,
                extra_banned_path=cfg.extra_banned_path,
                allowlist=cfg.allowlist,
                allowlist_path=cfg.allowlist_path,
                extra_allowlist=cfg.extra_allowlist,
                extra_allowlist_path=cfg.extra_allowlist_path,
                threshold=cfg.threshold,
                enable_fuzzy=cfg.enable_fuzzy,
                min_fuzzy_len=cfg.min_fuzzy_len,
                fuzzy_length_delta=cfg.fuzzy_length_delta,
                fuzzy_max_token_len=cfg.fuzzy_max_token_len,
                word_boundaries=cfg.word_boundaries,
                mask="vowels",
                normalize_leet=cfg.normalize_leet,
                normalize_separated_runs=cfg.normalize_separated_runs,
                normalize_repeated_chars=cfg.normalize_repeated_chars,
            )
        )
        assert vowels.clean(text) == case["expect_clean_vowels"], case["id"]
    return f


def corpus_hash(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode())
        h.update(b"\n")
    return h.hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class LatencySample:
    id: str
    text: str
    tags: frozenset[str]
    expect_contains: bool | None = None


def load_latency_samples() -> list[LatencySample]:
    cases = load_cases(PERF_ROOT / "latency_samples.yaml")
    out: list[LatencySample] = []
    for case in cases:
        out.append(
            LatencySample(
                id=case["id"],
                text=case["text"],
                tags=frozenset(case.get("tags") or []),
                expect_contains=case.get("expect_contains"),
            )
        )
    return out


def latency_sample_by_id(sample_id: str) -> LatencySample:
    for sample in load_latency_samples():
        if sample.id == sample_id:
            return sample
    raise KeyError(sample_id)


def load_throughput_profile(name: str = "default_mix") -> dict[str, Any]:
    profiles = load_yaml(PERF_ROOT / "throughput_profiles.yaml")["profiles"]
    if name not in profiles:
        raise KeyError(f"unknown throughput profile {name!r}; have {sorted(profiles)}")
    return dict(profiles[name])


def build_throughput_corpus(
    size: int,
    *,
    profile: str = "default_mix",
) -> tuple[list[str], dict[str, Any]]:
    """Deterministic synthetic corpus from a named mix profile."""
    if size < 0:
        raise ValueError("size must be >= 0")
    meta = load_throughput_profile(profile)
    templates: list[dict[str, Any]] = list(meta["templates"])
    weights = [int(t.get("weight", 1)) for t in templates]
    total_w = sum(weights)
    if total_w < 1:
        raise ValueError(f"profile {profile!r} has no template weight")

    # Expand weighted template list once for stable round-robin.
    bag: list[dict[str, Any]] = []
    for tmpl, w in zip(templates, weights, strict=True):
        bag.extend([tmpl] * w)

    out: list[str] = []
    for i in range(size):
        tmpl = bag[i % len(bag)]
        out.append(str(tmpl["text"]).format(i=i))
    info = {
        "profile": profile,
        "size": size,
        "corpus_hash": corpus_hash(out),
        "description": meta.get("description", ""),
        "template_count": len(templates),
    }
    return out, info
