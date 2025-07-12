import pytest


@pytest.mark.parametrize(
    "text, expected",
    [
        ("This is a clean sentence.", False),
        ("You are a b1tch!", True),  # fuzzy "bitch"
        ("What the fuck is going on?", True),  # exact "fuck"
        ("No bad words here.", False),
        ("Some people say shit sometimes.", True),  # exact "shit"
        (
            "This sentence has multiple bad words: ass, dick, and crap.",
            True,
        ),  # multiple exact
        ("eat my ass cupcake girl!!b0oooo0b!ies", True),  # fuzzy "boobies"
        ("What a lovely day!", False),
        ("D@mn, that was close!", False),
        ("You jerk!", False),
    ],
)
def test_has_profanity(profanity_filter_fixture, text, expected):
    assert profanity_filter_fixture.has_profanity(text) == expected
