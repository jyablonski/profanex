"""Validate release metadata shared by Python, Rust, locks, and the changelog."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_HEADING_RE = re.compile(r"^## \[([^]]+)] - (.+)$", re.MULTILINE)
FALLBACK_VERSION_RE = re.compile(r'^\s*__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def load_toml(path: str) -> dict[str, Any]:
    with (ROOT / path).open("rb") as handle:
        return tomllib.load(handle)


def package_versions(path: str, names: set[str]) -> dict[str, set[str]]:
    versions = {name: set() for name in names}
    for package in load_toml(path).get("package", []):
        name = package.get("name")
        if name in names:
            versions[name].add(str(package.get("version")))
    return versions


def validate_release() -> tuple[str, list[str]]:
    errors: list[str] = []
    project = load_toml("pyproject.toml")["project"]
    version = str(project["version"])

    match = STABLE_VERSION_RE.fullmatch(version)
    if match is None:
        errors.append(f"pyproject.toml version must be a stable X.Y.Z release, got {version!r}")
    elif tuple(map(int, match.groups())) < (1, 0, 0):
        errors.append(f"release version must be >= 1.0.0, got {version}")

    manifest_versions = {
        "pyproject.toml": version,
        "Cargo.toml": str(load_toml("Cargo.toml")["package"]["version"]),
        "crates/profanex-core/Cargo.toml": str(
            load_toml("crates/profanex-core/Cargo.toml")["package"]["version"]
        ),
    }
    for path, found in manifest_versions.items():
        if found != version:
            errors.append(f"{path} has version {found!r}; expected {version!r}")

    init_text = (ROOT / "profanex/__init__.py").read_text(encoding="utf-8")
    fallback_versions = FALLBACK_VERSION_RE.findall(init_text)
    if fallback_versions != [version]:
        errors.append(
            "profanex/__init__.py must contain exactly one fallback "
            f'__version__ = "{version}" assignment'
        )

    for lock_path, names in (
        ("Cargo.lock", {"profanex", "profanex-core"}),
        ("uv.lock", {"profanex"}),
    ):
        for name, found in package_versions(lock_path, names).items():
            if found != {version}:
                rendered = ", ".join(sorted(found)) or "missing"
                errors.append(
                    f"{lock_path} records {name} version(s) {rendered}; expected {version}"
                )

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(r"^## \[Unreleased]", changelog, re.MULTILINE | re.IGNORECASE):
        errors.append("CHANGELOG.md still contains an Unreleased section")
    heading = CHANGELOG_HEADING_RE.search(changelog)
    if heading is None:
        errors.append("CHANGELOG.md has no versioned release heading")
    else:
        changelog_version, release_date = heading.groups()
        if changelog_version != version:
            errors.append(
                f"first CHANGELOG.md release is {changelog_version!r}; expected {version!r}"
            )
        try:
            parsed_date = date.fromisoformat(release_date)
        except ValueError:
            errors.append(f"CHANGELOG.md release date must be YYYY-MM-DD, got {release_date!r}")
        else:
            if parsed_date.isoformat() != release_date:
                errors.append(f"CHANGELOG.md release date must be YYYY-MM-DD, got {release_date!r}")

    classifiers = project.get("classifiers", [])
    if "Development Status :: 5 - Production/Stable" not in classifiers:
        errors.append("pyproject.toml must classify a stable release as Production/Stable")

    return version, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-version",
        action="store_true",
        help="print only the validated release version",
    )
    args = parser.parse_args()

    version, errors = validate_release()
    if errors:
        for error in errors:
            print(f"release metadata error: {error}", file=sys.stderr)
        return 1

    if args.print_version:
        print(version)
    else:
        print(f"release metadata OK: {version}")
        print("manifests, lockfiles, Python fallback, changelog, and classifier agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
