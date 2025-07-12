import pytest


@pytest.mark.parametrize("style", ["stars", "vowel"])
def test_mask_styles(profanity_filter_fixture, style):
    profanity_filter_fixture.mask_style = style
    text = "This is crap and damn hell."
    masked = profanity_filter_fixture._mask_text(text, {"crap", "damn", "hell"})
    if style == "stars":
        assert all(
            ch == "*" for ch in masked if ch != " " and ch.lower() not in "thisisaand."
        )
    else:  # vowel style
        # vowels replaced with *, consonants remain
        for word in ["crap", "damn", "hell"]:
            masked_word = next(
                (w for w in masked.lower().split() if w.startswith(word[0])), ""
            )
            for v in "aeiou":
                if v in word:
                    assert "*" in masked_word
