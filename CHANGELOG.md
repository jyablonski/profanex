# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-15

### Added

- Rust matching engine using PyO3, maturin, and Aho-Corasick exact matching.
- Exact and multi-word phrase matching with opt-in fuzzy and evasive-text matching.
- Public `Filter`, `FilterConfig`, `Match`, `Category`, and `ConfigError` types.
- Deterministic `contains`, `find`, `clean`, and `analyze` operations built from one resolved match set.
- Unicode normalization with canonical composition, full case folding, and half-open spans into the original Python string.
- Category-aware packaged and custom YAML lexicons with consistent allowlist precedence.
- Ordered `*_many` and `iter_*` APIs with optional parallel processing.
- Fused `analyze` / `analyze_many` / `iter_analyze` APIs for callers that need both detection and cleaned text.
- Built-in star and vowel masks plus serial Python mask callbacks.
- Immutable configuration snapshots, bounded worker pools, and bounded fuzzy-match caching.
- Guarded leetspeak normalization that leaves numeric-only tokens unchanged, including beside non-Latin scripts.
- Indexed allowlist containment for predictable behavior on repeated allowed and banned terms.
- A precision-oriented default policy that excludes ambiguous homographs and context-neutral adult or anatomical terms.
- Contract, corpus, property, Unicode-invariant, and performance-sanity tests with CI packaging smoke installs.
- Reproducible accuracy and benchmark reporting, API and configuration guides, a documented threat model, and lexicon provenance.
