_SUBSTITUTIONS_MAP = {
    "1": "i",
    "!": "i",
    "3": "e",
    "4": "a",
    "@": "a",
    "5": "s",
    "$": "s",
    "7": "t",
    "0": "o",
    "9": "g",
    "*": "",
    "+": "t",
    "2": "z",
    "8": "b",
    "6": "g",
    "%": "x",
    "&": "and",
    "#": "h",
    "?": "",
    "-": "",
    ".": "",
    ",": "",
}


def normalize_text(text: str) -> str:
    """
    Normalize text by lowercasing and replacing leetspeak-style characters.

    Args:
        text (str): The input text to normalize.

    Returns:
        str: Normalized text with substitutions applied.
    """
    text = text.lower()
    return "".join(_SUBSTITUTIONS_MAP.get(c, c) for c in text)
