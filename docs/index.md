---
title: Profanex — fast profanity detection and filtering for Python
description: Rust-powered Python profanity filtering with Unicode-safe spans, fuzzy matching, allowlists, custom word lists, and parallel batch processing.
---

# Profanex

Profanex is a Rust-powered Python profanity filter for detecting, locating, and masking bad words and phrases. It is designed for deterministic content moderation with Unicode-safe spans, allowlists, optional fuzzy matching, configurable word lists, and parallel batch processing.

[![PyPI version](https://img.shields.io/pypi/v/profanex.svg)](https://pypi.org/project/profanex/)
[![Python versions](https://img.shields.io/pypi/pyversions/profanex.svg)](https://pypi.org/project/profanex/)
[![CI](https://github.com/jyablonski/profanex/actions/workflows/ci_cd.yaml/badge.svg)](https://github.com/jyablonski/profanex/actions/workflows/ci_cd.yaml)

## Install

```sh
uv add profanex
# or: python -m pip install profanex
```

## Detect and filter profanity

```python
from profanex import Filter

f = Filter()
text = "You are a b1tch!"

print(f.contains(text))  # True
print(f.find(text))
print(f.clean(text))     # You are a *****!
print(f.analyze(text))   # (True, "You are a *****!") from one scan
```

Every match contains a half-open span in Python string indexes, the source lexicon term, its categories, the match kind, and its fuzzy score. The same scan and overlap-resolution behavior is shared by `contains`, `find`, `clean`, and `analyze`.

## Why use Profanex?

- **Fast exact matching:** a Rust Aho-Corasick engine handles exact terms and multi-word phrases.
- **Unicode-safe results:** match spans index the original Python string, including case-fold expansions and astral characters.
- **Configurable moderation:** choose categories and combine packaged, custom, and application-specific banned and allowed terms.
- **Optional evasive-text detection:** enable fuzzy, repeated-character, or separated-run matching only when your policy needs it.
- **Scalable batch APIs:** preserve input order while processing collections serially or with bounded parallel workers.
- **Explicit tradeoffs:** defaults favor precision and predictable performance; benchmark methodology and tested limitations are documented.

## Choose the right configuration

Start with the defaults, then enable broader matching only against a representative validation corpus. The [configuration guide](configuration.md) explains recipes, false-positive controls, custom YAML lexicons, and performance implications.

For implementation details, normalization rules, and overlap resolution, see [How Profanex works](how_it_works.md). For measured latency and throughput on a documented host, see the [benchmark methodology and results](benchmarks.md).

Before choosing a production policy, review the [accuracy methodology](accuracy.md), [competitive benchmarks](competitive-benchmarks.md), complete [API reference](api.md), and [limitations and threat model](limitations.md).

## Project links

- [Source code](https://github.com/jyablonski/profanex)
- [PyPI package](https://pypi.org/project/profanex/)
- [Changelog](https://github.com/jyablonski/profanex/blob/main/CHANGELOG.md)
- [Issue tracker](https://github.com/jyablonski/profanex/issues)
- [Contributing guide](https://github.com/jyablonski/profanex/blob/main/CONTRIBUTING.md)
