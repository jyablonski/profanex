# Profanex

Profanex is a Python library for detecting and masking profanity in text using a combination of exact and fuzzy matching. It supports customizable banned and excluded word lists, configurable masking styles, and fast performance suitable for processing large volumes of text.

## Features

- Exact and fuzzy profanity detection with adjustable similarity threshold
- Masking profanity with configurable styles (e.g., stars)
- Load banned and excluded words from YAML files or directly via Python sets
- Excludes specific words from masking (e.g., “on”, “no”)
- Simple API with `has_profanity()` and `clean()` methods

## Installation

``` sh
pip install profanex
```

## Usage

``` py
from profanex import ProfanityFilter

pf = ProfanityFilter()

text = "You are a b1tch!"
if pf.has_profanity(text):
    clean_text = pf.clean(text)
    print(clean_text)  # Output: You are a *****!

```

## Performance

Profanex can process 10,000 average-length text entries in under 1.5 seconds on modern hardware, making it well-suited for both real-time and batch profanity filtering.

For larger workloads, Profanex supports parallel processing using Python's `concurrent.futures` module. When executed with `ProcessPoolExecutor`, Profanex can leverage all available CPU cores to efficiently clean or scan tens of thousands of texts in parallel with minimal overhead.

- See `scripts/benchmark_clean_parallel.py` for an Example

## Configuration

You can customize the banned and excluded word lists by providing your own YAML files or Python sets during initialization.
