# Profanex — fast profanity detection and filtering for Python

Profanex is a Rust-powered Python profanity filter for detecting, locating, and masking bad words and phrases. It provides Unicode-safe spans, allowlists, optional fuzzy matching, configurable word lists, and parallel batch processing.

[![PyPI version](https://img.shields.io/pypi/v/profanex.svg)](https://pypi.org/project/profanex/)
[![Python versions](https://img.shields.io/pypi/pyversions/profanex.svg)](https://pypi.org/project/profanex/)
[![CI](https://github.com/jyablonski/profanex/actions/workflows/ci_cd.yaml/badge.svg)](https://github.com/jyablonski/profanex/actions/workflows/ci_cd.yaml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://jyablonski.github.io/profanex/)
[![License: MIT + CC BY 4.0](https://img.shields.io/badge/license-MIT%20%2B%20CC--BY--4.0-blue.svg)](https://github.com/jyablonski/profanex/blob/main/LICENSE)

[Installation](#installation) · [Quick start](#quick-start) · [Configuration](#configuration) · [Documentation](https://jyablonski.github.io/profanex/) · [Benchmarks](https://jyablonski.github.io/profanex/benchmarks/)

## Why Profanex?

- A Rust-powered Aho-Corasick fast path for exact and multi-word phrase matching
- Unicode-safe Python string spans and consistent `contains`, `find`, and `clean` results
- Categories, allowlists, and custom YAML lexicons for application-specific moderation policies
- Optional fuzzy and evasion matching when recall matters more than raw throughput
- Ordered batch and iterator APIs with optional parallel processing

Defaults are conservative: all categories are enabled, word boundaries are enforced, and fuzzy and aggressive normalization are disabled.

## Requirements

- Python 3.11 or newer
- A supported abi3 prebuilt wheel (one wheel covers 3.11+), or Rust 1.85.0 and maturin when building from source

## Installation

```sh
uv add profanex
# or: python -m pip install profanex
```

For local development, see [CONTRIBUTING.md](https://github.com/jyablonski/profanex/blob/main/CONTRIBUTING.md).

## Quick start

```python
from profanex import Filter

f = Filter()
text = "You are a b1tch!"

print(f.contains(text))  # True
print(f.find(text))
print(f.clean(text))     # You are a *****!
print(f.analyze(text))   # (True, "You are a *****!") from one scan
```

Every match uses a half-open Python string span. Each `Match` also carries the lexicon `term`, `categories`, match `kind` (`exact` / `phrase` / `fuzzy`), and fuzzy `score` (100 for exact and phrase matches):

```python
match = f.find(text)[0]
assert match.text == text[match.start:match.end]
assert match.term and match.categories
```

`Filter.from_defaults()` is equivalent to `Filter()` / `Filter(FilterConfig())`.

## Configuration

```python
from profanex import Category, Filter, FilterConfig

config = FilterConfig(
    categories=frozenset(category for category in Category if category != Category.SLURS),
    extra_banned={"project-specific-term"},
    extra_allowlist=["projectcodename"],
    enable_fuzzy=True,
    threshold=85,
    mask="stars",
)
f = Filter(config)
```

| Option                                     | Default            | Purpose                                                                    |
| ------------------------------------------ | ------------------ | -------------------------------------------------------------------------- |
| `categories`                               | all                | Select enabled categories                                                  |
| `banned` / `banned_path`                   | packaged lexicon   | Replace the banned lexicon                                                 |
| `extra_banned` / `extra_banned_path`       | none               | Add banned terms                                                           |
| `allowlist` / `allowlist_path`             | packaged allowlist | Replace the allowlist                                                      |
| `extra_allowlist` / `extra_allowlist_path` | none               | Add allowed terms                                                          |
| `word_boundaries`                          | `True`             | Require Unicode word boundaries                                            |
| `normalize_leet`                           | `True`             | Apply the default leetspeak map                                            |
| `normalize_repeated_chars`                 | `False`            | Match repeated characters such as `fuuuck`                                 |
| `normalize_separated_runs`                 | `False`            | Match separated characters such as `f.u.c.k` / `f u c k`                   |
| `enable_fuzzy`                             | `False`            | Match similar single-token terms                                           |
| `threshold`                                | `85`               | Set the fuzzy score cutoff from 0 to 100                                   |
| `min_fuzzy_len`                            | `4`                | Ignore fuzzy tokens/terms shorter than this                                |
| `fuzzy_length_delta`                       | `2`                | Compare fuzzy terms within ±δ characters (maximum 64)                      |
| `fuzzy_max_token_len`                      | `64`               | Skip fuzzy tokens longer than this (maximum 256)                           |
| `mask`                                     | `"stars"`          | Use `"stars"`, `"vowels"` (ASCII vowels only), or a serial Python callback |

`banned` and `banned_path` cannot be used together; the same applies to `allowlist` and `allowlist_path`. Allowlist entries have final precedence after normalization, so an explicit allowed term can disable a packaged or custom banned term.

Default leet covers digit/`@`/`$` substitutions and infix `!→i` when the token contains an ASCII alphabetic anchor (for example `b1tch`, `a55`, `sh!t`). Numeric-only tokens such as `455` and `80085` are left unchanged even beside non-Latin text, and trailing `!` is unchanged. Common asterisk masks (`f*ck`, `sh*t`) are packaged lexicon literals. For stronger evasion (`fuuuck`, `f.u.c.k`), opt in:

```python
f = Filter(FilterConfig(
    normalize_repeated_chars=True,
    normalize_separated_runs=True,
))
```

Keep `enable_fuzzy=True` separate and measure it; it is off by default. For recipes, false-positive tradeoffs, and performance implications, see the [configuration guide](https://jyablonski.github.io/profanex/configuration/).

Custom YAML may be a flat list or a category mapping:

```yaml
general:
  - dang
sexual:
  - example-term
```

## Batch processing

Batch methods preserve input order. Parallel processing is opt-in:

```python
texts = ["clean", "what the fuck", "please pass"]

flags = f.contains_many(texts)
matches = f.find_many(texts)
cleaned = f.clean_many(texts, parallel=True, workers=4)
flags, cleaned = f.analyze_many(texts, parallel=True, workers=4)

# Streaming variants: iter_contains, iter_find, iter_clean, iter_analyze
streamed = list(f.iter_clean(texts, chunk_size=1_000))
```

Use `analyze` / `analyze_many` when both a flag and cleaned text are needed; they avoid scanning each input twice. Custom mask callbacks work only with serial cleaning. Explicit worker counts are capped at 256, and applications with their own thread pools should set a smaller value to avoid oversubscription.

## More information

- [Documentation](https://jyablonski.github.io/profanex/)
- [API reference](https://jyablonski.github.io/profanex/api/)
- [Configuration guide](https://jyablonski.github.io/profanex/configuration/) — when to enable each option and performance tradeoffs
- [How Profanex works](https://jyablonski.github.io/profanex/how_it_works/)
- [Accuracy methodology and results](https://jyablonski.github.io/profanex/accuracy/)
- [Benchmark methodology and results](https://jyablonski.github.io/profanex/benchmarks/)
- [Competitive benchmarks](https://jyablonski.github.io/profanex/competitive-benchmarks/)
- [Limitations and threat model](https://jyablonski.github.io/profanex/limitations/)
- [Fixture schema](https://github.com/jyablonski/profanex/blob/main/fixtures/README.md)
- [Lexicon provenance](https://github.com/jyablonski/profanex/blob/main/profanex/data/PROVENANCE.md) — upstream attribution, modifications, and data licensing
- [Release checklist](https://jyablonski.github.io/profanex/release-checklist/)

## License

The Profanex software is MIT licensed. The packaged banned lexicon is a modified CC BY 4.0 dataset; see [lexicon provenance](https://github.com/jyablonski/profanex/blob/main/profanex/data/PROVENANCE.md).
