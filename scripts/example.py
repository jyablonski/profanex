#!/usr/bin/env python3
"""Minimal demo of the 1.0 Filter API (not a packaging smoke test)."""

from __future__ import annotations

from profanex import Filter


def main() -> None:
    f = Filter()
    samples = [
        "This is a clean sentence.",
        "You are a b1tch!",
        "What the fuck is going on?",
        "please pass the salt",
    ]
    for text in samples:
        print(f"text={text!r}")
        print(f"  contains={f.contains(text)}")
        print(f"  find={f.find(text)}")
        print(f"  clean={f.clean(text)!r}")


if __name__ == "__main__":
    main()
