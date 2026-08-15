FROM python:3.13-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/.venv/bin:/root/.cargo/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=3.13 \
    CARGO_HOME=/root/.cargo \
    RUSTUP_HOME=/root/.rustup

# Pin matches rust-toolchain.toml / CI (1.85.0).
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl build-essential pkg-config && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.85.0 && \
    rustup component add rustfmt clippy && \
    rm -rf /var/lib/apt/lists/*

FROM base AS python-deps

ARG INSTALL_DEV_DEPENDENCIES=true

WORKDIR /src
COPY pyproject.toml uv.lock README.md Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY src ./src
COPY crates ./crates
COPY profanex ./profanex
COPY fixtures ./fixtures
COPY tests ./tests

# Pin matches CI UV_VERSION in .github/workflows/ci_cd.yaml.
RUN pip install uv==0.11.16 && \
    if [ "$INSTALL_DEV_DEPENDENCIES" = "true" ]; then \
      uv sync --frozen; \
    else \
      uv sync --frozen --no-dev; \
    fi && \
    uv run maturin develop --release --locked

FROM base AS runtime

COPY --from=python-deps /.venv /.venv
COPY --from=python-deps /src /src
ENV PATH="/.venv/bin:$PATH"

RUN useradd --create-home appuser
WORKDIR /home/appuser
USER appuser

WORKDIR /src
