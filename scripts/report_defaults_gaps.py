#!/usr/bin/env python3
"""Report out-of-box recall gaps from fixtures/corpora/defaults_out_of_box.yaml.

Compares actual Filter() (or per-case config) results to ``desired_contains`` when set.
Cases without ``desired_contains`` are treated as documentation-only for CI expects.

Usage:
  uv run python scripts/report_defaults_gaps.py
  uv run python scripts/report_defaults_gaps.py --group lexicon_gap
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from fixtures.loader import filter_from_case, load_suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", help="Only report this group")
    parser.add_argument(
        "--all-misses",
        action="store_true",
        help="Also list expect_contains=true cases that currently miss (CI would fail)",
    )
    args = parser.parse_args()

    cases = load_suite("corpora/defaults_out_of_box")
    if args.group:
        cases = [c for c in cases if c.get("group") == args.group]

    by_gap: dict[str, list[dict]] = defaultdict(list)
    hits = 0
    desired_gaps = 0
    ci_failures = 0

    print(f"Cases: {len(cases)}\n")
    for case in cases:
        f = filter_from_case(case)
        text = case["text"]
        got = f.contains(text)
        expect = case.get("expect_contains")
        desired = case.get("desired_contains", expect)
        terms = [m.term for m in f.find(text)]

        if expect is True and not got:
            ci_failures += 1
            if args.all_misses:
                print(f"CI FAIL  {case['id']}: {text!r} terms={terms}")

        if desired is None:
            continue

        if bool(desired) == got:
            hits += 1
            continue

        # Mismatch between aspiration and reality
        desired_gaps += 1
        gap = case.get("gap", "unclassified")
        by_gap[gap].append(case)
        status = "MISS" if desired and not got else "EXTRA"
        print(f"{status:5}  [{gap:16}] {case['id']:40} {text!r:30} got={got} terms={terms}")
        if case.get("notes"):
            print(f"       notes: {case['notes']}")

    print("\n--- Summary ---")
    print(f"Desired aligned: {hits}")
    print(f"Desired gaps:    {desired_gaps}")
    if ci_failures:
        print(f"CI expect fails:{ci_failures}")
    print("By gap class:")
    counts = Counter({k: len(v) for k, v in by_gap.items()})
    for gap, n in counts.most_common():
        print(f"  {gap:20} {n}")
    return 0 if ci_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
