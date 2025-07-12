import pytest

from profanex.normalize import normalize_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("You are a bitch", True),  # exact banned word
        ("This is damn good", True),
        ("No bad words here", False),
        ("jerkface", False),  # not exact "jerk"
        ("What the hell", False),
        ("Fuck yeah", True),
        ("Shitty situation", False),  # partial of "shit" but no exact match
    ],
)
def test_contains_profanity_exact(profanity_filter_manual_fixture, text, expected):
    # Use the method directly
    normalized = normalize_text(text=text)
    result = profanity_filter_manual_fixture._contains_profanity_exact(normalized)
    assert result is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("You are a bitcch", True),  # fuzzy close to "bitch"
        ("This is damnn good", True),  # fuzzy close to "damn"
        ("No bad words here", False),
        ("jerky behavior", True),  # fuzzy close to "jerk"
        ("What the hell", False),
        ("Shity situation", True),  # fuzzy close to "shit"
        ("completely clean", False),
    ],
)
def test_contains_profanity_fuzzy(profanity_filter_manual_fixture, text, expected):
    normalized = text.lower()  # Simulate normalization for testing
    result = profanity_filter_manual_fixture._contains_profanity_fuzzy(normalized)
    assert result is expected
