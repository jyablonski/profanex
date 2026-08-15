---
title: Profanex limitations and threat model
description: Scope, false-positive, false-negative, Unicode, evasion, fuzzy-matching, denial-of-service, privacy, and moderation limitations of Profanex.
---

# Limitations and threat model

Profanex is a deterministic dictionary-and-rules profanity filter. It is useful as one moderation signal, but it is not a complete content-safety, harassment, hate-speech, toxicity, or intent classifier.

## Language and policy scope

- The packaged lexicon is English-focused. Unicode-safe processing does not imply multilingual profanity coverage.
- Category assignments encode a maintainable default policy, not a universal judgment about every use of a term.
- Slang, reclaimed language, regional meanings, newly coined terms, names, and product-specific vocabulary require application review.
- Custom banned terms and allowlists are the preferred way to adapt policy without forking the packaged lexicon.

## No semantic context

Profanex recognizes text forms, not meaning or intent. It cannot reliably distinguish quotation, education, self-reference, consensual language, threats, targeted harassment, or a benign homograph. Conversely, abusive content can contain no profanity at all.

Do not use a Profanex result as the sole basis for irreversible account, employment, legal, medical, financial, or safety decisions. High-impact systems should combine explicit policy, contextual signals, appeal paths, and human review.

## False negatives

Defaults favor predictable performance and lower false-positive exposure. They can miss:

- unseen words, slang, inflections, and phrases absent from the effective lexicon;
- repeated or separated spellings unless the corresponding normalization option is enabled;
- transpositions and other misspellings when fuzzy matching is disabled;
- Cyrillic and other cross-script homoglyph substitutions;
- image, audio, encoded, encrypted, or otherwise non-textual content;
- adversarial forms outside the documented normalization rules.

Even the strongest built-in configuration is not an exhaustive adversarial detector. Measure misses on a held-out corpus from the target product.

## False positives

Word boundaries and the allowlist reduce substring failures such as matching a short term inside an innocent word. False positives can still arise from literal profane words used benignly, product names, proper nouns, domain jargon, fuzzy neighbors, or aggressive custom settings.

Keep word boundaries enabled unless substring matching is an explicit requirement. Add narrow allowlist entries for known false friends and evaluate fuzzy thresholds against a representative negative corpus.

## Unicode behavior

Profanex applies NFKC normalization, full case folding, Unicode word boundaries, and selected leetspeak substitutions while mapping accepted matches back to half-open indices in the original Python string. It does not implement a complete Unicode confusables skeleton or transliteration system. Visually similar characters from another script may therefore evade matching, and compatibility normalization can intentionally make distinct source sequences equivalent.

## Fuzzy matching and hostile inputs

Fuzzy matching is single-token, optional, and more expensive than exact matching. The engine bounds candidate lengths, length differences, and cache size, but an attacker can still send many distinct tokens to reduce cache reuse and increase CPU cost.

Applications exposed to untrusted traffic should:

- cap request and text size before calling Profanex;
- keep `fuzzy_max_token_len` bounded and the threshold conservative;
- benchmark diverse, miss-heavy inputs rather than only repeated cache hits;
- rate-limit abusive clients and enforce application-level time and resource budgets;
- avoid unnecessary worker pools or oversubscription.

Exact matching is linear in normalized input plus reported candidates, but Profanex does not impose a maximum input-text length. Sequence batch methods materialize their input and output; use iterator APIs with an explicit `chunk_size` for unbounded streams.

## Configuration and data trust

User YAML is parsed with `yaml.safe_load` and limited to 10 MiB per file. That protects against unsafe YAML object construction and unexpectedly large lexicon files, but configuration remains trusted policy input: very large in-memory lexicons, poorly chosen fuzzy settings, or an overbroad allowlist can still consume resources or undermine results.

The packaged banned lexicon is derived data under CC BY 4.0. Review [lexicon provenance](https://github.com/jyablonski/profanex/blob/main/profanex/data/PROVENANCE.md) before redistributing modified datasets.

## Privacy

Profanex performs matching locally, makes no network requests, and does not log source text or matched terms. The surrounding application is responsible for protecting inputs, moderation decisions, metrics, traces, and any stored corpus. Avoid placing raw sensitive text in logs or benchmark artifacts.

## Validation responsibility

The checked-in fixtures and synthetic generator protect known behavior and common evasion families; they are not independent evidence of production accuracy. Review the [accuracy methodology](accuracy.md), choose a configuration using the [configuration guide](configuration.md), and validate it against licensed, human-reviewed, production-shaped data before deployment.
