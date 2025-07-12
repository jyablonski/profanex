import pytest


@pytest.mark.parametrize(
    "text_input, expected_output",
    [
        ("What the hell is going on?", "What the hell is going on?"),
        ("You bitch better listen!", "You ***** better listen!"),
        ("Stop being a dumbass.", "Stop being a *******."),
        ("She's a camwhore bro.", "She's a ******** bro."),
        ("He's such a dick sometimes.", "He's such a **** sometimes."),
        ("What a bastard move.", "What a bastard move."),
        ("fuck you man", "**** you man"),
        ("Holy shit, that scared me.", "Holy ****, that scared me."),
        ("You shit!", "You ****!"),
        ("Such a boobs day.", "Such a ***** day."),
    ],
)
def test_clean_general(profanity_filter_fixture, text_input, expected_output):
    result = profanity_filter_fixture.clean(text_input)
    assert result == expected_output
