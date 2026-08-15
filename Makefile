.PHONY: develop test rust-test rust-cov build docs docs-serve accuracy benchmark-competitors fmt lint typecheck quality clippy deadcode check prerelease-check release

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

check: develop quality test

prerelease-check:
	python3 scripts/check_release.py
	$(MAKE) check
	$(MAKE) docs
	$(MAKE) build

# just run `make release`, no need to set a version. it reads the version from pyproject.toml
release:
	@branch="$$(git branch --show-current)"; \
		if [ "$$branch" != "main" ]; then \
			echo "release must run from main (current branch: $$branch)" >&2; \
			exit 1; \
		fi
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "release requires a clean working tree" >&2; \
		git status --short; \
		exit 1; \
	fi
	@git fetch origin --tags
	@if [ "$$(git rev-parse HEAD)" != "$$(git rev-parse origin/main)" ]; then \
		echo "local main must exactly match origin/main before release" >&2; \
		exit 1; \
	fi
	@version="$$(python3 scripts/check_release.py --print-version)"; \
		tag="v$$version"; \
		if git show-ref --verify --quiet "refs/tags/$$tag"; then \
			echo "tag $$tag already exists" >&2; \
			exit 1; \
		fi; \
		printf "Create and push %s from main at %s? [y/N] " "$$tag" "$$(git rev-parse --short HEAD)"; \
		read answer; \
		case "$$answer" in y|Y|yes|YES) ;; *) echo "release cancelled"; exit 1 ;; esac; \
		git tag -a "$$tag" -m "Profanex $$version"; \
		if ! git push origin "$$tag"; then \
			echo "tag push failed; $$tag remains local" >&2; \
			exit 1; \
		fi; \
		echo "pushed $$tag; monitor the CI/CD workflow for publication"
