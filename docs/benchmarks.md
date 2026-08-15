---
title: Python profanity-filter benchmarks
description: Reproducible Profanex latency, throughput, fuzzy-matching, batch-processing, and Polars benchmark methodology and results.
---

# Benchmarks

Benchmark results are specific to a host, corpus, and configuration. Exact and fuzzy results must be reported separately. For which config knobs affect latency and when to enable them, see the [configuration guide](configuration.md).

For product-default measurements against other Python packages, see [competitive benchmarks](competitive-benchmarks.md). For classification metrics and their dataset limitations, see the [accuracy report](accuracy.md).

Normal CI runs only broad performance sanity tests. Use these scripts for measured latency, throughput, and parallel crossover:

```sh
uv run maturin develop --uv --release
uv run python scripts/benchmark_latency.py --write benchmarks/results/latency.json
uv run python scripts/benchmark_throughput.py --profile default_mix --size 5000 --write benchmarks/results/throughput.json
uv run python scripts/benchmark_batch_crossover.py
uv run --with 'polars>=1,<2' python scripts/benchmark_polars.py --rows 100000
```

Generated JSON under `benchmarks/results/` is ignored. Commit only reviewed summaries to this document.

## Inputs

Performance inputs live under [`fixtures/perf/`](https://github.com/jyablonski/profanex/tree/main/fixtures/perf):

| File                       | Purpose                                      |
| -------------------------- | -------------------------------------------- |
| `latency_samples.yaml`     | Named texts for single-item latency          |
| `throughput_profiles.yaml` | Weighted templates for deterministic batches |

The API and accuracy fixtures under [`fixtures/api/`](https://github.com/jyablonski/profanex/tree/main/fixtures/api) and [`fixtures/corpora/`](https://github.com/jyablonski/profanex/tree/main/fixtures/corpora) validate the same public behavior.

## Required metadata

Record the following with every published result:

- Profanex version or commit
- Fixture name, corpus profile, size, and hash
- Python version, operating system, and CPU
- Exact or fuzzy configuration
- Warmup, repetitions, and worker count
- Whether filter construction is included

Do not compare results across different hosts or corpora as if they were equivalent.

## Polars DataFrame example

The Polars benchmark builds a 100,000-row DataFrame with `id` and `review_text`, processes the text through Profanex's batch API, and adds `contains_profanity` and `review_text_cleaned` columns:

```sh
uv run maturin develop --uv --release
uv run --with 'polars>=1,<2' python scripts/benchmark_polars.py --rows 100000
```

Use `--serial` to compare serial processing, `--workers N` to bound the Rayon thread pool, or `--write-parquet benchmarks/results/reviews.parquet` to inspect the resulting DataFrame. Generation and filter construction are excluded from the reported time; conversion from the Polars string column, one fused `analyze_many` call, and assembly of the two result columns are included.

### Local 100,000-row result

This local release-build run used Profanex 1.0.0, Python 3.14.5, Polars 1.43.2, Linux 7.1.8 x86_64 with glibc 2.44, five measured repetitions after a 5,000-row warmup, and a corpus containing 10% profane reviews. Synthetic DataFrame generation and filter construction were excluded.

| Mode                      | `analyze_many` | End-to-end median | Throughput       |
| ------------------------- | -------------: | ----------------: | ---------------: |
| Parallel, default workers |       0.0282 s |          0.0380 s | 2,628,764 rows/s |
| Serial                    |       0.0921 s |          0.1003 s |   997,327 rows/s |

On this host and corpus, default parallel processing was approximately 2.64× faster end to end. Compared with the prior two-scan example, the fused parallel path reduced end-to-end median time from 0.0534 s to 0.0380 s on this host; treat that comparison as directional because the kernel version also changed.

## Accepted Rust baseline

This is a local release-build baseline, not a hardware-independent performance claim.

### Environment

- Profanex: 1.0.0 local editable release build
- Base commit: `ce8c3cfb4357`, plus the working-tree Unicode/scan/fuzzy/FFI pass described in the 1.0 changelog
- Python: 3.14.5
- Platform: Linux 7.1.8-arch1-3, x86_64, glibc 2.44
- CPU: Intel Core i9-10900K @ 3.70GHz (10c/20t)
- Throughput profile: `default_mix`, 5,000 texts
- Corpus hash: `3165dc392ec8c3f1`
- Latency: 20 warmups, 201 measured calls
- Throughput: median of five measured batches
- Filter construction: excluded

Refresh with the commands at the start of this document. Compare only on the same host, corpus, and mode.

### Single-item latency

| Operation                   | p50 µs | p95 µs | p99 µs |
| --------------------------- | -----: | -----: | -----: |
| Exact clean `contains`      |   2.71 |   3.78 |   4.26 |
| Exact matched `contains`    |   1.37 |   2.39 |   2.52 |
| Exact matched `find`        |   5.01 |  10.26 |  10.55 |
| Exact matched `clean`       |   2.50 |   2.94 |   3.16 |
| Exact matched `analyze`     |   1.83 |   3.03 |   4.12 |
| Exact phrase `find`         |   5.23 |   9.84 |  10.30 |
| Exact long clean `contains` |   8.73 |  14.24 |  15.02 |
| Exact long dense `find`     |  36.77 |  55.15 |  62.67 |
| Fuzzy typo warm `contains`  |   1.65 |   1.78 |   2.01 |
| Fuzzy typo warm `find`      |   1.69 |   2.68 |   3.02 |
| Fuzzy unique cold `contains` | 66.92 | 189.83 | 222.98 |

The warm fuzzy rows repeatedly query the packaged default filter and intentionally show cache-hit latency. The cold row uses 221 deterministic custom terms and a different one-edit token for every call, so it measures cache misses under a unique-token workload; it is not directly comparable to the default-lexicon warm row.

### Batch throughput

| Operation                        | Median ms |    Texts/s |
| -------------------------------- | --------: | ---------: |
| Exact `contains_many`, serial    |      7.34 |   ~681,000 |
| Exact `contains_many`, 2 workers |      4.12 | ~1,214,000 |
| Exact `clean_many`, serial       |      7.22 |   ~692,000 |
| Exact `analyze_many`, serial     |      7.07 |   ~707,000 |
| Fuzzy `contains_many`, serial    |     10.32 |   ~485,000 |
| Fuzzy `contains_many`, 2 workers |      5.45 |   ~917,000 |
| Fuzzy `analyze_many`, serial     |     11.67 |   ~428,000 |

### Prior baseline (pre P0/P1 pass)

Same host/corpus for regression attribution:

| Metric                       | Previous |  Current | Change |
| ---------------------------- | -------: | -------: | -----: |
| Exact clean `contains` p50   |  3.05 µs |  2.71 µs |   −11% |
| Exact `contains_many` serial |  ~550k/s |  ~681k/s |  +24% |
| Fuzzy typo warm `contains` p50 | 35.28 µs | 1.65 µs | −95% |
| Fuzzy `contains_many` serial |   ~14k/s |  ~485k/s |   ~35× |

### Regression policy

- Compare only the same host, corpus, and mode.
- Investigate regressions greater than 20%.
- Keep exact and fuzzy results separate.
- Use `tests/test_perf_sanity.py` only as an algorithmic ceiling, not a numeric regression gate.

## Parallel batch crossover

Parallel processing is disabled by default because it adds overhead to small batches and may oversubscribe applications that already use thread pools.

This local run used the `crossover` profile from `fixtures/perf/throughput_profiles.yaml`, discarded warmup work, and recorded median times. On this host, two workers became faster around 200 texts.

Refresh the table with `uv run python scripts/benchmark_batch_crossover.py`.

### Auto-recorded run

Corpus profile: `crossover` (`fixtures/perf/throughput_profiles.yaml`).

| N texts | serial ms | parallel(workers=2) ms | parallel(default) ms | notes |
|---|---:|---:|---:|---|
| 50 | 0.057 | 0.049 | 0.104 | speedup_w2=1.16x |
| 200 | 0.236 | 0.159 | 0.158 | speedup_w2=1.48x |
| 1000 | 1.202 | 0.778 | 0.434 | speedup_w2=1.54x |
| 5000 | 9.166 | 3.447 | 1.653 | speedup_w2=2.66x |
| 20000 | 22.697 | 13.103 | 4.711 | speedup_w2=1.73x |
