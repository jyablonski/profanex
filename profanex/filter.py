import logging
from pathlib import Path
import re
from typing import Any
import yaml

from rapidfuzz import fuzz

from profanex.normalize import normalize_text

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _load_yaml(filepath: str) -> set[str]:
    """
    Load a YAML list (or category-grouped dict) of words.

    Args:
        filepath: Path to a YAML file containing either a flat list or
            a dictionary of categories whose values are lists of words.

    Returns:
        A set with all words from the file.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Could not find file at {filepath}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    all_words = set()

    for words in data.values():
        all_words.update(words)
    return all_words


class ProfanityFilter:
    def __init__(
        self,
        *,
        banned_words: set[str] | None = None,
        mask_style: str = "stars",
        banned_words_path: str | None = "profanex/data/banned_words.yaml",
        excluded_words: set[str] | None = None,
        excluded_words_path: str | None = "profanex/data/excluded_words.yaml",
        threshold: int = 80,
        debug_mode: bool = False,
    ):
        if banned_words is not None:
            self.banned_words = banned_words
        else:
            self.banned_words = _load_yaml(banned_words_path)

        if excluded_words is not None:
            self.excluded_words = excluded_words
        else:
            self.excluded_words = _load_yaml(excluded_words_path)

        self.mask_style = mask_style
        self.threshold = threshold
        self.debug_mode = debug_mode

        if self.debug_mode:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    # ---------------------------------------------------------------------
    #                             Public API
    # ---------------------------------------------------------------------

    def has_profanity(self, text: str) -> bool:
        """
        Method to check if the input text contains profanity.
        It normalizes the text and checks for both exact and fuzzy matches,
        returning True if any profanity is found and False otherwise.

        Args:
            text (str): The input text to check for profanity.

        Returns:
            bool: True if profanity is detected, False otherwise.
        """
        normalized = normalize_text(text=text)

        if self._contains_profanity_exact(text=normalized):
            return True

        # if both return False, then the text has no profanity
        return self._contains_profanity_fuzzy(text=normalized, threshold=self.threshold)

    def clean(self, text: str) -> str:
        """
        Method to clean the input text by masking profanity.
        It checks for both exact and fuzzy matches against banned words.

        Args:
            text (str): The input text to clean.

        Returns:
            str: The cleaned text with profanity masked according to the mask style.
        """
        words_to_mask = self._gather_direct_matches(text) | self._gather_fuzzy_matches(
            text
        )
        words_to_mask -= self._excluded()

        if not words_to_mask:
            return text

        return self._mask_text(text=text, words_to_mask=words_to_mask)

    # ---------------------------------------------------------------------
    #                            Private API
    # ---------------------------------------------------------------------

    def _get_fuzzy_matches(
        self, text: str, threshold: int | None = None
    ) -> list[tuple[Any, str, int]]:
        """Return all words whose similarity to a banned word >= *threshold*.

        Args:
            text: Text to scan (should already be normalized).
            threshold: Override the instance threshold if provided.

        Returns:
            A list of ``(input_word, banned_word, similarity_score)`` tuples.
        """
        threshold = threshold or self.threshold
        words = re.findall(r"\w+", text)
        matches = []

        for input_word in words:
            for banned_word in self.banned_words:
                score = fuzz.ratio(input_word, banned_word)
                if score >= threshold:
                    matches.append((input_word, banned_word, score))
        return matches

    def _contains_profanity_fuzzy(
        self, text: str, threshold: int | None = None
    ) -> bool:
        """Check if *text* contains any fuzzy profanity.

        Args:
            text: Normalized input string.

            threshold: Override the instance threshold if provided.

        Returns:
            ``True`` if a fuzzy match is found, else ``False``.
        """
        threshold = threshold or self.threshold
        for word, banned_word, score in self._get_fuzzy_matches(text, threshold):
            # Early-exit: the first match is enough
            logger.debug(f"Fuzzy hit: {word} ≈ {banned_word} ({score})")
            return True
        return False

    def _contains_profanity_exact(self, text: str) -> bool:
        """
        Check if any word in the input text directly matches a banned word.

        This uses exact matching (not normalized or fuzzy).

        Args:
            text: The input string to scan.

        Returns:
            True if any word in the text is found in the banned words set; otherwise, False.
        """
        words = re.findall(r"\w+", text)
        return any(word in self.banned_words for word in words)

    def _gather_direct_matches(self, text: str) -> set[str]:
        """
        Return original tokens whose normalized form matches a banned word.

        Args:
            text (str): The raw input text.

        Returns:
            set[str]: A set of original words that matched directly after normalization.
        """
        tokens = re.findall(r"\w+", text)
        normalized = {token: normalize_text(token) for token in tokens}
        return {tok for tok, norm in normalized.items() if norm in self.banned_words}

    def _gather_fuzzy_matches(self, text: str) -> set[str]:
        """
        Return original tokens that fuzz-match a banned word (≥ threshold).

        Args:
            text (str): The raw input text.

        Returns:
            set[str]: A set of original words whose normalized form matched fuzzily.
        """
        norm_text = normalize_text(text=text)
        fuzzy_input_words = {m[0] for m in self._get_fuzzy_matches(norm_text)}
        tokens = re.findall(r"\w+", text)
        return {tok for tok in tokens if normalize_text(tok) in fuzzy_input_words}

    def _excluded(self) -> set[str]:
        """
        Return words that should never be masked (case-insensitive).

        Returns:
            set[str]: A lowercase set of words excluded from masking.
        """
        return {w.lower() for w in self.excluded_words}

    def _mask_text(self, text: str, words_to_mask: set[str]) -> str:
        """
        Replace matched words in the original text using the chosen mask style.

        Args:
            text (str): The original input text.

            words_to_mask (set[str]): Words to mask (case-insensitive).

            style (str): Masking style - "stars" masks entire word with '*',
                        "vowel" masks only vowels.

        Returns:
            str: The masked text.
        """

        def replace(match: re.Match) -> str:
            word = match.group(0)
            if self.mask_style == "vowel":
                return re.sub(r"[aeiouAEIOU]", "*", word)
            return "*" * len(word)

        pattern = re.compile(
            r"\b(" + "|".join(map(re.escape, words_to_mask)) + r")\b",
            flags=re.IGNORECASE,
        )
        return pattern.sub(replace, text)
