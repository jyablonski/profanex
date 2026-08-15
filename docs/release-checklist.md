# Release checklist

Publishing is triggered by pushing a version tag (`v*`). Pull requests and normal pushes to `main` never publish packages.

## Before the release

- [ ] Choose the release version and update `CHANGELOG.md`.
- [ ] Set matching versions in `pyproject.toml`, `Cargo.toml`, and `crates/profanex-core/Cargo.toml` (Python fallback in `profanex/__init__.py` if used).
- [ ] Skim [lexicon provenance](https://github.com/jyablonski/profanex/blob/main/profanex/data/PROVENANCE.md); confirm the banned lexicon still carries required upstream attribution, a CC BY 4.0 link, and a description of material changes.
- [ ] Confirm that README examples and defaults match the implementation.
- [ ] Ensure `Cargo.lock` and `uv.lock` are committed (reproducible CI / maturin builds).
- [ ] Confirm workspace `rust-version` matches `rust-toolchain.toml` / CI (currently 1.85).
- [ ] Run `make check` (includes Python vulture + Rust cargo-machete deadcode checks).
- [ ] Build a wheel and sdist locally, install each in a clean environment, change to a temporary directory, and confirm that `Filter()` loads packaged resources.
- [ ] Confirm that CI is green on the release commit (PR or `main`).
- [ ] Run `make accuracy`; update the accuracy snapshot if the lexicon, normalization, fuzzy behavior, or evaluation corpus changed.
- [ ] Run `make benchmark-competitors` before repeating or changing comparative performance claims; record package versions, corpus hash, and host metadata.
- [ ] Run `make docs` and review the generated documentation locally.

## Publish the release

1. Update the changelog with the release date.
2. Commit and tag the release, for example `v1.0.0` (**the tag must equal** `v` + the `pyproject.toml` version).
3. Push the tag. CI runs tests and builds wheels before the **Publish release** job verifies the version, uploads artifacts to GitHub, and publishes to PyPI through trusted publishing.
4. Verify https://pypi.org/project/profanex/ and install the published wheel in a clean environment.
5. Run a short API and packaged-resource smoke test from outside the repository.
6. Request indexing for the documentation homepage in Google Search Console and submit `https://jyablonski.github.io/profanex/sitemap.xml` when documentation URLs change.

## One-time repository setup

1. Create a protected GitHub environment named `pypi`.
2. Configure [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) for this repository and `.github/workflows/ci_cd.yaml` (tag / environment as required by PyPI).
3. In **Settings → Pages**, select **GitHub Actions** as the source; the documentation workflow will build pull requests and deploy pushes to `main`.
4. Set the GitHub repository description to “Fast Rust-powered profanity detection and filtering for Python” and the website to `https://jyablonski.github.io/profanex/`.
5. Add focused repository topics: `python`, `rust`, `profanity-filter`, `profanity-detection`, `bad-word-filter`, `content-moderation`, `text-filtering`, `fuzzy-matching`, `unicode`, and `pyo3`.
6. Upload a legible 1280×640 repository social preview that includes the project name and “Fast profanity filtering for Python.”
7. Ensure `SLACK_WEBHOOK_URL` is available to the workflow if you want deploy notifications (`jyablonski/actions/deploy-notification`).

The workflow builds Linux / macOS / Windows wheels plus the sdist before publish. Native-arch wheels are smoke-imported (Linux `x86_64` on the Ubuntu runner; all macOS and Windows matrix entries). Cross-compiled Linux arches are build-verified only. Do not bypass failed jobs or publish local, untested artifacts.
