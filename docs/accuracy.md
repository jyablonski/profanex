---
title: Profanity-detection accuracy methodology and results
description: Reproducible Profanex precision, recall, F1, false-positive, policy-contract, and synthetic evasion results with explicit limitations.
---

# Accuracy methodology and results

Profanity detection has no universal ground truth: policies differ across products, communities, languages, and contexts. This report therefore separates regression-contract conformance from synthetic evasion measurements and does not present either as real-world production accuracy.

## Reproduce the report

```sh
uv run maturin develop --uv --release
uv run python -m scripts.evaluate_accuracy
```

The script executes the checked-in contract fixtures, generates a deterministic synthetic corpus, evaluates four documented configurations, prints the confusion matrices, and can write machine-readable output with `--write benchmarks/results/accuracy.json`.

## Contract conformance

On August 12, 2026, Profanex 1.0.0 passed all **153** curated behavior contracts: 90 positive and 63 negative cases drawn from `defaults_out_of_box.yaml`, `tp.yaml`, and `fp.yaml`.

This is a regression result, not an accuracy estimate. These cases were written to specify intended behavior and are part of the test suite; they are not an independently sampled evaluation set.

## Synthetic evasion evaluation

The deterministic generator produced 800 cases from seed `20260801`, with corpus hash `bcf47186aba0adbd`: 757 generated positives and 43 clean or allowlist-shaped negatives. It covers plain terms, case changes, leetspeak, repeated characters, separated runs, asterisk masks, misspellings, fullwidth text, Cyrillic lookalikes, phrases, embeddings, and combinations of those transformations.

Local environment: Profanex 1.0.0, Python 3.14.5, Linux 7.1.8 x86-64, Intel Core i9-10900K. Metrics are deterministic for a given Profanex build, seed, and corpus generator; the CPU does not affect the classification results.

| Configuration | Precision | Recall | F1 | False-positive rate | TP / FP / TN / FN |
|---|---:|---:|---:|---:|---:|
| Default | 100.0% | 28.7% | 44.6% | 0.0% | 217 / 0 / 43 / 540 |
| Repeated + separated normalization | 100.0% | 61.3% | 76.0% | 0.0% | 464 / 0 / 43 / 293 |
| Fuzzy, threshold 85 | 98.7% | 41.6% | 58.6% | 9.3% | 315 / 4 / 39 / 442 |
| Repeated + separated + fuzzy 85 | 99.3% | 72.4% | 83.7% | 9.3% | 548 / 4 / 39 / 209 |

The results illustrate the intended policy tradeoff: default matching is conservative, normalization recovers structural evasion without introducing false positives in this small negative set, and fuzzy matching adds typo recall while increasing false-positive exposure. The small, curated negative set makes the displayed precision and false-positive percentages especially uncertain; they should not be extrapolated to production traffic.

## Metric definitions

- **Precision:** `TP / (TP + FP)` — how often a positive result was correct in this corpus.
- **Recall:** `TP / (TP + FN)` — how many labeled positives were detected.
- **F1:** harmonic mean of precision and recall.
- **False-positive rate:** `FP / (FP + TN)` — how many labeled negatives were incorrectly detected.

## What this report does not establish

- It does not measure accuracy on naturally occurring user text.
- Its seed vocabulary and transformation generator were designed alongside Profanex, so it is not independent.
- Labels identify generated profanity forms, not whether a phrase is abusive or inappropriate in context.
- The 43 negatives are far too few to estimate a production false-positive rate.
- It does not cover every dialect, new slang term, language, homoglyph, or adversarial encoding.
- It must not be used to claim a universally applicable accuracy percentage.

For a deployment decision, build a separate, licensed, human-reviewed corpus sampled from the target product; keep it outside the tuning loop; report confidence intervals; and evaluate each intended configuration against that held-out set. See [Limitations and threat model](limitations.md) for the remaining policy and security boundaries.
