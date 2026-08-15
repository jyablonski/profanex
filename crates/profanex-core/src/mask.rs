//! Masking strategies over original-space spans.

use crate::resolve::MatchCandidate;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MaskStyle {
    Stars,
    Vowels,
}

fn is_vowel(ch: char) -> bool {
    matches!(ch.to_ascii_lowercase(), 'a' | 'e' | 'i' | 'o' | 'u')
}

fn mask_with(text: &str, matches: &[MatchCandidate], map_char: impl Fn(char) -> char) -> String {
    if matches.is_empty() {
        return text.to_string();
    }
    let mut out = String::with_capacity(text.len());
    let mut cursor = 0usize;
    for m in matches {
        if m.orig_start < cursor || m.orig_end > text.len() || m.orig_start > m.orig_end {
            continue;
        }
        if !text.is_char_boundary(m.orig_start) || !text.is_char_boundary(m.orig_end) {
            continue;
        }
        out.push_str(&text[cursor..m.orig_start]);
        for ch in text[m.orig_start..m.orig_end].chars() {
            out.push(map_char(ch));
        }
        cursor = m.orig_end;
    }
    out.push_str(&text[cursor..]);
    out
}

/// Replace each Unicode scalar in each match span with `*`.
pub fn mask_stars(text: &str, matches: &[MatchCandidate]) -> String {
    mask_with(text, matches, |_| '*')
}

/// Mask documented ASCII vowels inside each match span.
pub fn mask_vowels(text: &str, matches: &[MatchCandidate]) -> String {
    mask_with(text, matches, |ch| if is_vowel(ch) { '*' } else { ch })
}

pub fn apply_mask(text: &str, matches: &[MatchCandidate], style: MaskStyle) -> String {
    match style {
        MaskStyle::Stars => mask_stars(text, matches),
        MaskStyle::Vowels => mask_vowels(text, matches),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::exact::MatchKind;

    fn cand(start: usize, end: usize) -> MatchCandidate {
        MatchCandidate {
            orig_start: start,
            orig_end: end,
            norm_start: start,
            norm_end: end,
            pattern_id: 0,
            categories: 1,
            score: 100.0,
            kind: MatchKind::Exact,
        }
    }

    #[test]
    fn stars_and_vowels() {
        assert_eq!(apply_mask("hello", &[], MaskStyle::Stars), "hello");
        assert_eq!(
            apply_mask("a foul word", &[cand(2, 6)], MaskStyle::Stars),
            "a **** word"
        );
        assert_eq!(
            apply_mask("a foul word", &[cand(2, 6)], MaskStyle::Vowels),
            "a f**l word"
        );
    }

    #[test]
    fn skips_invalid_spans() {
        let text = "abcd";
        // overlapping / backwards / past end / mid-char should be ignored
        let bad = [
            cand(2, 1),
            cand(0, 99),
            cand(3, 2),
            MatchCandidate {
                orig_start: 1,
                orig_end: 1,
                norm_start: 0,
                norm_end: 0,
                pattern_id: 0,
                categories: 1,
                score: 100.0,
                kind: MatchKind::Exact,
            },
        ];
        // empty-range match is char-boundary-valid but masks nothing
        assert_eq!(mask_stars(text, &bad), "abcd");
    }
}
