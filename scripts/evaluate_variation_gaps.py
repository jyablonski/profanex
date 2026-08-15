#!/usr/bin/env python3
"""Generate obfuscation variations and classify default Filter() recall gaps.

Produces 500–1000 synthetic variants from high-signal lexicon seeds, then
evaluates catch rate under:
  - default Filter() (leet on, fuzzy/repeated/separated off, word boundaries on)
  - progressive opt-ins that explain misses (repeated, separated, fuzzy, WB off)

Also samples clean / allowlist-shaped negatives so false-positive pressure is visible.

Usage:
  uv run maturin develop --release
  uv run python scripts/evaluate_variation_gaps.py
  uv run python scripts/evaluate_variation_gaps.py --target 800 --write benchmarks/results/variation_gaps.json
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from profanex import Filter, FilterConfig, __version__

# High-signal single-token seeds (must already be in defaults or closely related).
# Phrases are handled separately with lighter mutation.
SEED_SINGLES = [
    "fuck",
    "shit",
    "bitch",
    "ass",
    "asshole",
    "cunt",
    "cock",
    "piss",
    "pissed",
    "pussy",
    "whore",
    "slut",
    "bastard",
    "damn",
    "crap",
    "arse",
    "bollocks",
    "wanker",
    "prick",
    "faggot",
    "nigger",
    "retard",
    "motherfucker",
    "fucking",
    "shitty",
    "bitches",
    "dicks",
    "cocks",
    "porn",
    "tits",
    "boobs",
    "rape",
    "kill",
    "murder",
]

SEED_PHRASES = [
    "blow job",
    "son of a bitch",
    "piece of shit",
]

# Should stay clean under defaults (allowlist / innocent).
CLEAN_NEGATIVES = [
    "classic",
    "password",
    "assassin",
    "assess",
    "assume",
    "bass",
    "compass",
    "cocktail",
    "scunthorpe",
    "shitake",  # often FP; may or may not be listed
    "hello world",
    "thank you",
    "beautiful day",
    "mississippi",
    "grasshopper",
    "cassette",
    "accumulate",
    "title",
    "button",
    "butter",
    "assistant",
    "passage",
    "glass",
    "class",
    "mass",
    "Order 455 shipped",
    "product code 80085",
    "anal fissure",
    "police escort",
    "erotic art",
    "league domination",
    "The big black dog ran home",
    "She graduated cum laude",
    "Dick Van Dyke starred in it",
    "The horse was ridden bareback",
    "Repair the earthen dike",
    "Use a butt joint here",
    "He made a boner in the report",
    "The detective was dogging the suspect",
    "The exercise balls are blue",
    "Two asses carried the load",
    "455中",
    "ก80085",
]

LEET_MAP = {
    "a": ["4", "@"],
    "e": ["3"],
    "i": ["1", "!"],
    "o": ["0"],
    "s": ["5", "$"],
    "t": ["7"],
    "b": ["8"],
}


@dataclass(frozen=True)
class Variant:
    text: str
    seed: str
    family: str
    expected_positive: bool


def _swap_leet(word: str, rng: random.Random, max_subs: int = 2) -> str:
    chars = list(word)
    idxs = [i for i, c in enumerate(chars) if c.lower() in LEET_MAP]
    rng.shuffle(idxs)
    for i in idxs[:max_subs]:
        opts = LEET_MAP[chars[i].lower()]
        chars[i] = rng.choice(opts)
    return "".join(chars)


def _insert_separators(word: str, rng: random.Random, sep: str) -> str:
    if len(word) < 3:
        return word
    # Single-char runs: f.u.c.k
    return sep.join(word)


def _repeat_chars(word: str, rng: random.Random) -> str:
    if len(word) < 2:
        return word
    i = rng.randrange(len(word))
    n = rng.randint(3, 5)
    return word[:i] + word[i] * n + word[i + 1 :]


def _transpose(word: str, rng: random.Random) -> str:
    if len(word) < 3:
        return word
    i = rng.randrange(len(word) - 1)
    chars = list(word)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def _drop_char(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word
    i = rng.randrange(len(word))
    return word[:i] + word[i + 1 :]


def _dup_char(word: str, rng: random.Random) -> str:
    if not word:
        return word
    i = rng.randrange(len(word))
    return word[: i + 1] + word[i] + word[i + 1 :]


def _asterisk_mask(word: str, rng: random.Random) -> str:
    if len(word) < 3:
        return word
    chars = list(word)
    # Mask 1–2 interior vowels/consonants
    interior = list(range(1, len(chars) - 1))
    rng.shuffle(interior)
    for i in interior[: rng.randint(1, min(2, len(interior)))]:
        chars[i] = "*"
    return "".join(chars)


def _unicode_lookalike(word: str) -> str:
    # Common confusables / fullwidth / combining
    table = str.maketrans(
        {
            "a": "а",  # Cyrillic a
            "e": "е",  # Cyrillic e
            "o": "о",  # Cyrillic o
            "c": "с",  # Cyrillic s-looking
            "p": "р",  # Cyrillic r-looking
            "x": "х",
            "y": "у",
        }
    )
    return word.translate(table)


def _fullwidth(word: str) -> str:
    out = []
    for ch in word:
        if "!" <= ch <= "~":
            out.append(chr(ord(ch) - ord("!") + 0xFF01))
        else:
            out.append(ch)
    return "".join(out)


def _embed(word: str, rng: random.Random) -> str:
    prefixes = ["xx", "my", "the", "super", "ultra", ""]
    suffixes = ["xx", "er", "ing", "ed", "y", ""]
    return f"{rng.choice(prefixes)}{word}{rng.choice(suffixes)}"


def _sentence(word: str, rng: random.Random) -> str:
    templates = [
        "what the {w}",
        "you absolute {w}",
        "oh {w}",
        "this is {w}",
        "{w} off",
        "go {w} yourself",
        "such a {w}",
    ]
    return rng.choice(templates).format(w=word)


def generate_variants(rng: random.Random, target: int) -> list[Variant]:
    out: list[Variant] = []
    seen: set[str] = set()

    def add(text: str, seed: str, family: str, positive: bool = True) -> None:
        key = text.casefold()
        if not text.strip() or key in seen:
            return
        seen.add(key)
        out.append(Variant(text=text, seed=seed, family=family, expected_positive=positive))

    # Deterministic core set first (coverage of each family).
    for seed in SEED_SINGLES:
        add(seed, seed, "plain")
        add(seed.upper(), seed, "case")
        add(seed.capitalize(), seed, "case")
        add(_sentence(seed, rng), seed, "sentence")
        add(_swap_leet(seed, rng, 1), seed, "leet_light")
        add(_swap_leet(seed, rng, 3), seed, "leet_heavy")
        add(_insert_separators(seed, rng, "."), seed, "sep_dot")
        add(_insert_separators(seed, rng, "*"), seed, "sep_star")
        add(_insert_separators(seed, rng, "_"), seed, "sep_underscore")
        add(_insert_separators(seed, rng, " "), seed, "sep_space")
        add(_repeat_chars(seed, rng), seed, "repeated")
        add(_transpose(seed, rng), seed, "typo_transpose")
        add(_drop_char(seed, rng), seed, "typo_drop")
        add(_dup_char(seed, rng), seed, "typo_dup")
        add(_asterisk_mask(seed, rng), seed, "asterisk_mask")
        add(_unicode_lookalike(seed), seed, "unicode_cyrillic")
        add(_fullwidth(seed), seed, "unicode_fullwidth")
        add(_embed(seed, rng), seed, "embedded")
        # Compound obfuscations
        add(_swap_leet(_repeat_chars(seed, rng), rng, 2), seed, "leet_plus_repeat")
        add(_insert_separators(_swap_leet(seed, rng, 1), rng, "."), seed, "leet_plus_sep")

    for phrase in SEED_PHRASES:
        add(phrase, phrase, "phrase_plain")
        add(phrase.replace(" ", "   "), phrase, "phrase_spaces")
        add(phrase.replace(" ", "-"), phrase, "phrase_hyphen")
        add(_swap_leet(phrase, rng, 2), phrase, "phrase_leet")

    for neg in CLEAN_NEGATIVES:
        add(neg, neg, "negative_clean", positive=False)

    # Fill remaining budget with random mutations from seeds.
    families = [
        ("leet_light", lambda s: _swap_leet(s, rng, 1)),
        ("leet_heavy", lambda s: _swap_leet(s, rng, 3)),
        ("sep_dot", lambda s: _insert_separators(s, rng, ".")),
        ("sep_star", lambda s: _insert_separators(s, rng, "*")),
        ("repeated", lambda s: _repeat_chars(s, rng)),
        ("typo_transpose", lambda s: _transpose(s, rng)),
        ("typo_drop", lambda s: _drop_char(s, rng)),
        ("asterisk_mask", lambda s: _asterisk_mask(s, rng)),
        ("embedded", lambda s: _embed(s, rng)),
        ("sentence", lambda s: _sentence(_swap_leet(s, rng, 1), rng)),
        ("leet_plus_repeat", lambda s: _swap_leet(_repeat_chars(s, rng), rng, 2)),
        ("case_leet", lambda s: _swap_leet(s.upper(), rng, 2)),
    ]
    while len(out) < target:
        seed = rng.choice(SEED_SINGLES)
        family, fn = rng.choice(families)
        add(fn(seed), seed, family)
        if len(seen) > target * 3:
            break

    return out[:target]


@dataclass
class EvalRow:
    text: str
    seed: str
    family: str
    expected_positive: bool
    default_hit: bool
    default_terms: list[str]
    gap: str | None


def classify_gap(
    text: str,
    *,
    default_hit: bool,
    expected_positive: bool,
    seed: str,
    lexicon_terms: set[str],
    filters: dict[str, Filter],
) -> str | None:
    if not expected_positive:
        return "false_positive" if default_hit else None
    if default_hit:
        return None

    # Seed (or phrase) absent from banned list → lexicon gap, not an engine limitation.
    seed_key = seed.casefold()
    if seed_key not in lexicon_terms:
        return "lexicon_missing_seed"

    # Progressive explanation order (most specific opt-in first).
    if filters["repeated"].contains(text):
        return "needs_repeated"
    if filters["separated"].contains(text):
        return "needs_separated"
    if filters["repeated_separated"].contains(text):
        return "needs_repeated_and_separated"
    if filters["fuzzy"].contains(text):
        return "needs_fuzzy"
    if filters["fuzzy_repeated"].contains(text):
        return "needs_fuzzy_plus_normalize"
    if filters["no_wb"].contains(text):
        return "word_boundary"
    if filters["kitchen_sink"].contains(text):
        return "needs_all_opt_ins"
    return "uncovered"  # not caught even with all opt-ins on this seed


def load_lexicon_terms() -> set[str]:
    import yaml

    path = Path(__file__).resolve().parents[1] / "profanex" / "data" / "banned_words.yaml"
    data = yaml.safe_load(path.read_text())
    return {str(w).casefold() for words in data.values() for w in words}


def build_filters() -> dict[str, Filter]:
    return {
        "default": Filter(),
        "repeated": Filter(FilterConfig(normalize_repeated_chars=True)),
        "separated": Filter(FilterConfig(normalize_separated_runs=True)),
        "repeated_separated": Filter(
            FilterConfig(normalize_repeated_chars=True, normalize_separated_runs=True)
        ),
        "fuzzy": Filter(FilterConfig(enable_fuzzy=True, threshold=75)),
        "fuzzy_repeated": Filter(
            FilterConfig(
                enable_fuzzy=True,
                threshold=75,
                normalize_repeated_chars=True,
                normalize_separated_runs=True,
            )
        ),
        "no_wb": Filter(FilterConfig(word_boundaries=False)),
        "kitchen_sink": Filter(
            FilterConfig(
                enable_fuzzy=True,
                threshold=70,
                normalize_repeated_chars=True,
                normalize_separated_runs=True,
                word_boundaries=False,
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=800, help="Number of variants (500–1000)")
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--write", type=Path, help="Optional JSON report path")
    parser.add_argument("--show-misses", type=int, default=40, help="Sample misses to print")
    args = parser.parse_args()
    target = max(500, min(1000, args.target))

    rng = random.Random(args.seed)
    variants = generate_variants(rng, target)
    filters = build_filters()
    default = filters["default"]
    lexicon_terms = load_lexicon_terms()

    rows: list[EvalRow] = []
    gap_counts: Counter[str] = Counter()
    family_stats: dict[str, Counter[str]] = defaultdict(Counter)

    for v in variants:
        hit = default.contains(v.text)
        terms = [m.term for m in default.find(v.text)] if hit else []
        gap = classify_gap(
            v.text,
            default_hit=hit,
            expected_positive=v.expected_positive,
            seed=v.seed,
            lexicon_terms=lexicon_terms,
            filters=filters,
        )
        rows.append(
            EvalRow(
                text=v.text,
                seed=v.seed,
                family=v.family,
                expected_positive=v.expected_positive,
                default_hit=hit,
                default_terms=terms,
                gap=gap,
            )
        )
        if gap:
            gap_counts[gap] += 1
        family_stats[v.family]["n"] += 1
        if v.expected_positive:
            family_stats[v.family]["pos"] += 1
            if hit:
                family_stats[v.family]["caught"] += 1
            else:
                family_stats[v.family]["miss"] += 1
        else:
            family_stats[v.family]["neg"] += 1
            if hit:
                family_stats[v.family]["fp"] += 1

    positives = [r for r in rows if r.expected_positive]
    negatives = [r for r in rows if not r.expected_positive]
    caught = sum(1 for r in positives if r.default_hit)
    missed = len(positives) - caught
    fps = sum(1 for r in negatives if r.default_hit)

    print(f"Profanex {__version__}  Python {platform.python_version()}")
    print(f"Variants: {len(rows)}  (seed={args.seed}, target={target})")
    print()
    print("=== Default Filter() recall ===")
    print(f"  Positives: {len(positives)}")
    print(f"  Caught:    {caught}  ({100 * caught / len(positives):.1f}%)")
    print(f"  Missed:    {missed}  ({100 * missed / len(positives):.1f}%)")
    print(f"  Negatives: {len(negatives)}  false positives: {fps}")
    print()
    print("=== Gap classification (misses / FPs) ===")
    for gap, n in gap_counts.most_common():
        print(f"  {gap:28} {n:4}")
    print()
    print("=== By variation family (positives) ===")
    print(f"  {'family':22} {'n':>5} {'caught':>7} {'miss':>5} {'recall':>7}")
    for family in sorted(family_stats.keys()):
        st = family_stats[family]
        pos = st["pos"]
        if pos == 0:
            continue
        caught_f = st["caught"]
        miss_f = st["miss"]
        recall = 100 * caught_f / pos
        print(f"  {family:22} {pos:5} {caught_f:7} {miss_f:5} {recall:6.1f}%")

    print()
    print("=== Negative / FP families ===")
    for family in sorted(family_stats.keys()):
        st = family_stats[family]
        if st["neg"] == 0:
            continue
        print(f"  {family:22} n={st['neg']}  fp={st['fp']}")

    # Sample misses by gap class
    print()
    print(f"=== Sample misses (up to {args.show_misses}) ===")
    shown = 0
    by_gap: dict[str, list[EvalRow]] = defaultdict(list)
    for r in rows:
        if r.gap and r.expected_positive:
            by_gap[r.gap].append(r)
    for gap, items in sorted(by_gap.items(), key=lambda kv: -len(kv[1])):
        for r in items[: max(1, args.show_misses // max(1, len(by_gap)))]:
            print(f"  [{gap:24}] seed={r.seed!r:16} text={r.text!r} terms={r.default_terms}")
            shown += 1
            if shown >= args.show_misses:
                break
        if shown >= args.show_misses:
            break

    # Kitchen-sink residual: true blind spots
    uncovered = [r for r in rows if r.gap == "uncovered"]
    print()
    print(f"=== Uncovered even with kitchen-sink opt-ins: {len(uncovered)} ===")
    for r in uncovered[:30]:
        print(f"  seed={r.seed!r:16} family={r.family:18} text={r.text!r}")

    report = {
        "profanex_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "seed": args.seed,
        "variant_count": len(rows),
        "positives": len(positives),
        "caught": caught,
        "missed": missed,
        "recall_pct": round(100 * caught / len(positives), 2) if positives else 0.0,
        "negatives": len(negatives),
        "false_positives": fps,
        "gap_counts": dict(gap_counts),
        "family_stats": {k: dict(v) for k, v in family_stats.items()},
        "uncovered_sample": [asdict(r) for r in uncovered[:50]],
        "miss_sample": [asdict(r) for r in rows if r.gap and r.expected_positive][:100],
    }
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nWrote {args.write}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
