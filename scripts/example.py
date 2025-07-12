import logging

from profanex import ProfanityFilter


def main():
    # Instantiate the filter (loads banned words from YAML by default)
    pf = ProfanityFilter(debug_mode=True)

    test_texts = [
        "This is a clean sentence.",
        "You are a b1tch!",
        "What the fuck is going on?",
        "No bad words here.",
        "Some people say shit sometimes.",
        "This sentence has multiple bad words: ass, dick, and crap.",
        "eat my ass cupcake girl!!b0oooo0b!ies",
    ]

    for text in test_texts:
        logging.info(f"Does {text} have profanity: {pf.has_profanity(text)}")

    for text in test_texts:
        cleaned = pf.clean(text)
        logging.info(f"Original: {text}")
        logging.info(f"Cleaned: {cleaned}")
        logging.info("-" * 40)


if __name__ == "__main__":
    main()
