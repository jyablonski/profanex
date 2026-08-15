---
title: Python profanity-filter competitive benchmarks
description: Reproducible default-policy latency and throughput comparisons between Profanex, better-profanity, BadWords, and alt-profanity-check.
---

# Competitive benchmarks

This comparison measures the documented public detection API of each package under its packaged English defaults. It is a product-level benchmark, not a pure matching-engine benchmark: the libraries use different lexicons, normalization, algorithms, and batch interfaces. Hit counts are reported beside throughput so timing differences are not mistaken for equivalent policy behavior.

## Reproduce

```sh
uv run --no-project --python 3.12 \
  --with . \
  --with better-profanity==0.7.0 \
  --with badwords-py==2.3.1 \
  --with alt-profanity-check==1.9.0 \
  python -m scripts.benchmark_competitors
```

The packages are isolated from Profanex's runtime and development dependencies. Profanex uses serial `contains_many`; alt-profanity-check uses its vectorized `predict`; libraries without a batch detection API are called once per input. Initialization and imports are excluded. Each single-text result is the median of 201 calls after 20 warmups; each batch result is the median of five 5,000-text runs.

## Local result

Measured August 11, 2026 on Python 3.12.12, Linux 7.1.8 x86-64 with glibc 2.44, Intel Core i9-10900K. Corpus: `default_mix`, 5,000 texts, hash `3165dc392ec8c3f1`.

| Library | Version | Architecture | Clean `contains` p50 | Matched `contains` p50 | Batch texts/s | Positive results |
|---|---:|---|---:|---:|---:|---:|
| Profanex | 1.0.0 | Rust rules | 2.43 µs | 1.25 µs | 1,030,518 | 1,251 |
| better-profanity | 0.7.0 | Python rules | 7,304.29 µs | 4,529.46 µs | 255 | 1,252 |
| BadWords | 2.3.1 | Rust rules | 9.53 µs | 2.16 µs | 186,922 | 1,250 |
| alt-profanity-check | 1.9.0 | scikit-learn model | 2,757.35 µs | 2,727.37 µs | 271,530 | 1,250 |

On this host and corpus, Profanex had the lowest single-item latency and highest serial/default batch throughput among these tested package versions. That statement is deliberately narrow: different hardware, thread settings, corpora, policy configuration, package releases, and APIs can change the result. In particular, alt-profanity-check amortizes substantial per-call overhead through vectorized prediction, while Profanex's batch API crosses the Python boundary once.

## Selection rationale

- [better-profanity](https://pypi.org/project/better-profanity/) is a widely used pure-Python dictionary and leetspeak baseline.
- [BadWords](https://pypi.org/project/badwords-py/) is a current Rust-backed rules and evasion-detection library and the closest architectural comparison.
- [alt-profanity-check](https://pypi.org/project/alt-profanity-check/) is a maintained scikit-learn classifier with materially different contextual and performance tradeoffs.

The harness intentionally excludes the unmaintained original `profanity-check` and packages that cannot install on the benchmark interpreter without legacy system dependencies.

## Interpretation rules

- Do not interpret throughput as accuracy. The [accuracy report](accuracy.md) evaluates Profanex configurations separately and also documents its dataset limitations.
- Do not interpret near-equal hit counts as equivalent matches; packages may flag different rows.
- Do not compare these numbers with vendor-published results from other machines.
- Re-run before making a release claim, pin every package version, and retain the complete JSON output with `--write benchmarks/results/competitors.json`.
- Compare cleaning, spans, fuzzy modes, and parallel execution separately when those capabilities matter; this table covers default boolean detection only.
