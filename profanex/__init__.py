"""Profanex: dictionary/rules-based profanity detection and masking."""

from importlib.metadata import PackageNotFoundError, version

from profanex.api import Filter, FilterConfig, Match
from profanex.lexicon import Category, ConfigError

__all__ = [
    "Category",
    "ConfigError",
    "Filter",
    "FilterConfig",
    "Match",
    "__version__",
]

try:
    __version__ = version("profanex")
except PackageNotFoundError:  # pragma: no cover - uninstalled source tree
    __version__ = "1.0.0"
