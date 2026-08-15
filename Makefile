.PHONY: develop test rust-test rust-cov build docs docs-serve accuracy benchmark-competitors fmt lint typecheck quality clippy deadcode check

develop:
	uv sync --group local
	uv run maturin develop --uv --locked

test: develop
	uv run pytest
	cargo test --locked -p profanex-core

rust-test:
	cargo test --locked -p profanex-core --all-targets

rust-cov:
	cargo llvm-cov --locked -p profanex-core --all-targets --fail-under-lines 90 --html --output-dir coverage/html

build:
	uv run maturin build --release --locked -o dist
	uv run maturin sdist -o dist

docs:
	uv sync --locked --only-group docs --no-install-project
	uv run --no-sync mkdocs build --strict

docs-serve:
	uv sync --locked --only-group docs --no-install-project
	uv run --no-sync mkdocs serve

accuracy: develop
	uv run python -m scripts.evaluate_accuracy

benchmark-competitors:
	uv run --no-project --python 3.12 --with . \
		--with better-profanity==0.7.0 \
		--with badwords-py==2.3.1 \
		--with alt-profanity-check==1.9.0 \
		python -m scripts.benchmark_competitors

fmt:
	cargo fmt --all
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run ty check

clippy:
	cargo clippy --locked --workspace --all-targets -- -D warnings

# Python: vulture unused code. Rust: cargo-machete unused crate deps (+ clippy -D warnings covers dead_code).
deadcode:
	uv run vulture profanex fixtures scripts tests \
		--exclude '*_core.pyi' \
		--min-confidence 80
	@command -v cargo-machete >/dev/null 2>&1 || { \
		echo "cargo-machete not found; install with:"; \
		echo "  cargo install cargo-machete --version 0.7.0 --locked"; \
		echo "(CI installs a prebuilt cargo-machete 0.8.0 binary)"; \
		exit 1; \
	}
	cargo machete

quality: lint typecheck deadcode
	cargo fmt --all -- --check
	$(MAKE) clippy

check: quality test
