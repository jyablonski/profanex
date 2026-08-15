# Fixtures

Tests and benchmark scripts share the canonical inputs in this directory through `fixtures.loader`.

## Layout

| Path | Purpose |
|---|---|
| `api/*.yaml` | Public API behavior, errors, masks, categories, and batches |
| `corpora/*.yaml` | True positives, false positives, Unicode, overlaps, fuzzy, and out-of-box recall |
| `perf/latency_samples.yaml` | Single-item benchmark inputs |
| `perf/throughput_profiles.yaml` | Deterministic batch profiles |
| `loader.py` | Loading, filter construction, and assertion helpers |

## Out-of-box recall

`corpora/defaults_out_of_box.yaml` exercises `Filter()` defaults (leet on, fuzzy off, repeated/separated off). Cases may use:

| Field | Meaning |
|---|---|
| `expect_contains` | Required CI behavior |
| `expect_terms` | Term strings that must appear (no span list required) |
| `desired_contains` | Aspirational OOB behavior for gap review |
| `gap` | Gap class (`lexicon`, `word_boundary`, `needs_repeated`, …) |

Generate a gap report:

```sh
uv run python scripts/report_defaults_gaps.py
```

## Case format

Every case has a unique `id` and usually a `text` value. Other fields are optional:

| Field | Meaning |
|---|---|
| `config` | `FilterConfig` keyword arguments |
| `expect_contains` | Expected boolean result |
| `expect_terms` | Term strings that must appear (span-free recall checks) |
| `expect_matches` / `expect` | Ordered match data |
| `desired_contains` | Aspirational result for gap reports (not enforced by pytest) |
| `gap` / `notes` / `group` | Gap classification metadata |
| `expect_clean_stars` | Expected star-mask result |
| `expect_clean_vowels` | Expected vowel-mask result |
| `expect_error` | Text required in a `ConfigError` |
| `tags` | Benchmark labels |

Match spans use half-open Python string indexes. When `config` is omitted, the default policy enables all categories and word boundaries while leaving fuzzy matching off.

Run fixture-driven tests with:

```sh
uv run pytest tests/test_fixture_suites.py
```
