from pathlib import Path

import pytest
from profanex import ProfanityFilter


@pytest.fixture(scope="function")
def profanity_filter_fixture() -> ProfanityFilter:
    """ProfanityFilter instance for tests."""
    pf = ProfanityFilter()
    return pf


@pytest.fixture(scope="function")
def profanity_filter_manual_fixture() -> ProfanityFilter:
    """ProfanityFilter instance for tests."""
    pf = ProfanityFilter(
        banned_words={"bitch", "damn", "fuck", "shit", "jerk"},
        excluded_words={"nice", "kind"},
        threshold=80,
    )
    return pf


@pytest.fixture(scope="function")
def profanity_filter_debug_fixture() -> ProfanityFilter:
    """ProfanityFilter instance for tests."""
    pf = ProfanityFilter(debug_mode=True)
    return pf


@pytest.fixture
def banned_words_path_fixture() -> Path:
    # Path to your existing test fixture file
    return Path(__file__).parent / "data" / "banned_words.yaml"
