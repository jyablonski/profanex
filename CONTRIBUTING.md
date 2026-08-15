# Contributing

## Prerequisites

- Python 3.11 or newer
- Rust 1.85.0, selected by `rust-toolchain.toml`
- [uv](https://docs.astral.sh/uv/)

## Set up the project

```sh
uv sync --group local
uv run maturin develop --uv --locked
uv run pytest
cargo test --locked -p profanex-core
```

The Python tests build coverage reports and require at least 90% line coverage. Rust coverage additionally requires `cargo-llvm-cov`.

Deadcode checks (`make deadcode`) need [vulture](https://pypi.org/project/vulture/) (via the `quality` dependency group) and [cargo-machete](https://crates.io/crates/cargo-machete). On Rust 1.85, install `cargo-machete` 0.7.x from source (`cargo install cargo-machete --version 0.7.0 --locked`); newer machete releases need a newer rustc to *build*, while CI installs a prebuilt 0.8.0 binary. Clippy with `-D warnings` already fails on unused Rust items (`dead_code`).

Common commands:

```sh
make develop    # install dependencies and build the extension
make test       # run Python and Rust tests
make build      # build a release wheel and sdist for the current platform (--locked)
make docs       # build the documentation in strict mode
make accuracy   # reproduce policy-contract and synthetic-evasion metrics
make benchmark-competitors  # run pinned product-default comparisons on Python 3.12
make deadcode   # vulture (Python) + cargo-machete (Rust deps)
make check      # format, lint, type-check, deadcode, and test
make prerelease-check  # validate release metadata and run checks, docs, and package builds
make release    # from clean, current main: validate, create, and push the release tag
```

## Project layout

| Path                    | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| `profanex/`             | Public Python API, configuration, and YAML loading |
| `src/lib.rs`            | Private PyO3 extension module                      |
| `crates/profanex-core/` | Pure Rust matching engine                          |
| `Cargo.lock`            | Locked Rust dependency versions (commit this file) |
| `fixtures/`             | Shared API, accuracy, and performance inputs       |
| `tests/`                | Python contract and integration tests              |
| `benchmarks/`           | Benchmark method and recorded results              |
| `docs/configuration.md` | Config recipes, tradeoffs, and performance notes   |
| `docs/api.md`           | Generated public Python API reference              |
| `docs/accuracy.md`      | Accuracy methodology, results, and caveats         |
| `docs/limitations.md`   | Scope, safety boundaries, and hostile-input risks  |

The native extension is required. If importing `profanex._core` fails, run `uv run maturin develop`.

## Before opening a pull request

```sh
pre-commit run --all-files
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo machete
uv run vulture profanex fixtures scripts tests --exclude '*_core.pyi' --min-confidence 80
uv run pytest
```

Keep public behavior in `fixtures/` when possible so API tests and benchmarks use the same inputs. Update the README or changelog when public API, defaults, packaging, or lexicon policy changes.

Before opening a release pull request, run `make prerelease-check`. After that pull request is merged and `main` is green, maintainers can run `make release`; its tag push starts the publishing workflow.
