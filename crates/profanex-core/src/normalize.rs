//! Conservative normalization with original UTF-8 byte range maps.

use unicode_casefold::UnicodeCaseFold;
use unicode_normalization::UnicodeNormalization;
use unicode_segmentation::UnicodeSegmentation;

/// Options for the normalization pipeline.
#[derive(Debug, Clone, Copy)]
pub struct NormalizeOptions {
    pub normalize_leet: bool,
    /// Collapse whitespace / hyphen runs to a single space (phrase-friendly).
    pub canonical_separators: bool,
    /// Collapse alphabetic runs of length >= 3 to a single character (`fuuuck` → `fuck`).
    pub normalize_repeated_chars: bool,
    /// Join constrained single-character runs separated by `.` `*` `_` or space
    /// (`f.u.c.k` / `f u c k` → `fuck`).
    pub normalize_separated_runs: bool,
}

impl Default for NormalizeOptions {
    fn default() -> Self {
        Self {
            normalize_leet: true,
            canonical_separators: true,
            normalize_repeated_chars: false,
            normalize_separated_runs: false,
        }
    }
}

/// Minimum alphabetic run length before repeated-char squash applies.
pub const REPEAT_MIN_RUN: usize = 3;

/// Minimum number of single characters in a separated run before joining.
pub const SEPARATED_MIN_CHARS: usize = 3;

fn is_glue_sep(ch: char) -> bool {
    // Space included so opt-in `normalize_separated_runs` also joins `f u c k`.
    // Defaults leave this pass off; canonical_separators already collapses whitespace runs.
    matches!(ch, '.' | '*' | '_' | ' ')
}

/// Normalized haystack plus per-scalar original byte ranges.
#[derive(Debug, Clone)]
pub struct NormalizedText {
    pub text: String,
    /// For each Unicode scalar in `text`, half-open byte range in the original string.
    pub char_ranges: Vec<(usize, usize)>,
    /// Normalized-text byte offset of each scalar; length is `char_ranges.len() + 1`
    /// with the final entry equal to `text.len()`.
    pub char_norm_starts: Vec<usize>,
    /// Byte offsets in `text` that are Unicode word boundaries (sorted, unique).
    ///
    /// `None` means boundaries have not been built yet. Call [`Self::ensure_boundaries`]
    /// before [`Self::is_boundary`] or fuzzy tokenization. An empty `Some(vec)` is valid
    /// for empty text; never treat unbuilt as "no boundaries".
    pub boundary_bytes: Option<Vec<usize>>,
}

impl NormalizedText {
    fn rebuild_char_index(&mut self) {
        self.char_norm_starts.clear();
        self.char_norm_starts.reserve(self.char_ranges.len() + 1);
        let mut byte_pos = 0usize;
        for ch in self.text.chars() {
            self.char_norm_starts.push(byte_pos);
            byte_pos += ch.len_utf8();
        }
        self.char_norm_starts.push(byte_pos);
        debug_assert_eq!(byte_pos, self.text.len());
    }

    /// Build UAX#29 word-boundary byte offsets if not already present.
    pub fn ensure_boundaries(&mut self) {
        if self.boundary_bytes.is_none() {
            self.boundary_bytes = Some(word_boundary_bytes(&self.text));
        }
    }

    /// Map a half-open byte range in normalized text to original UTF-8 bytes.
    pub fn project_bytes(&self, norm_start: usize, norm_end: usize) -> Option<(usize, usize)> {
        if norm_start > norm_end || norm_end > self.text.len() {
            return None;
        }
        if norm_start == norm_end {
            if norm_start != self.text.len() && !self.text.is_char_boundary(norm_start) {
                return None;
            }
            let idx = self.char_norm_starts.partition_point(|&b| b < norm_start);
            let pos = if idx < self.char_ranges.len() {
                self.char_ranges[idx].0
            } else {
                self.char_ranges.last().map(|(_, e)| *e).unwrap_or(0)
            };
            return Some((pos, pos));
        }
        if !self.text.is_char_boundary(norm_start) || !self.text.is_char_boundary(norm_end) {
            return None;
        }

        let start_idx = self.char_norm_starts.partition_point(|&b| b < norm_start);
        let end_idx = self.char_norm_starts.partition_point(|&b| b < norm_end);
        if start_idx >= end_idx || end_idx > self.char_ranges.len() {
            return None;
        }

        let (orig_start, _) = self.char_ranges[start_idx];
        let (_, orig_end) = self.char_ranges[end_idx - 1];
        if orig_start <= orig_end {
            Some((orig_start, orig_end))
        } else {
            None
        }
    }

    pub fn is_boundary(&self, byte_offset: usize) -> bool {
        let bounds = self
            .boundary_bytes
            .as_ref()
            .expect("ensure_boundaries before is_boundary");
        bounds.binary_search(&byte_offset).is_ok()
    }
}

fn leet_subst(ch: char) -> Option<char> {
    match ch {
        '0' => Some('o'),
        '1' => Some('i'),
        '3' => Some('e'),
        '4' => Some('a'),
        '@' => Some('a'),
        '5' => Some('s'),
        '$' => Some('s'),
        '7' => Some('t'),
        '8' => Some('b'),
        // `!` is handled contextually (infix only) so trailing `Fuck!` stays intact.
        // `*` has no safe single-letter fold; common masks are lexicon literals.
        _ => None,
    }
}

fn is_leet_token_char(ch: char, include_separated_glue: bool) -> bool {
    ch.is_alphanumeric()
        || matches!(ch, '@' | '$' | '!')
        || (include_separated_glue && matches!(ch, '.' | '*' | '_'))
}

/// Fold `!`→`i` only when both neighbors are alphanumeric (`sh!t`→`shit`, not `fuck!`→`fucki`).
fn fold_leet_char(
    ch: char,
    prev_out: Option<char>,
    next_in: Option<char>,
    token_has_alpha: bool,
) -> char {
    // Numeric-only identifiers such as order 455 or 80085 are much more common
    // than all-digit profanity spellings. Require an alphabetic anchor in the
    // surrounding token before interpreting digits/symbols as letters. Callers
    // provide an ASCII anchor because this substitution table is English/Latin.
    if !token_has_alpha {
        return ch;
    }
    if ch == '!' {
        let prev_ok = prev_out.is_some_and(char::is_alphanumeric);
        let next_ok = next_in.is_some_and(char::is_alphanumeric);
        if prev_ok && next_ok {
            return 'i';
        }
        return '!';
    }
    leet_subst(ch).unwrap_or(ch)
}

fn is_separator(ch: char) -> bool {
    ch.is_whitespace() || ch == '-'
}

fn push_mapped_char(
    text: &mut String,
    char_ranges: &mut Vec<(usize, usize)>,
    out_ch: char,
    orig: (usize, usize),
) {
    text.push(out_ch);
    char_ranges.push(orig);
}

/// Normalize `input` and build an original-byte range map (always includes word boundaries).
pub fn normalize(input: &str, opts: NormalizeOptions) -> NormalizedText {
    normalize_ex(input, opts, true)
}

/// Normalize `input`. When `build_boundaries` is false, skip UAX#29 boundary indexing
/// (boundaries can still be built later via [`NormalizedText::ensure_boundaries`]).
pub fn normalize_ex(input: &str, opts: NormalizeOptions, build_boundaries: bool) -> NormalizedText {
    let mut norm = if input.is_ascii() {
        normalize_ascii(input, opts)
    } else {
        normalize_unicode(input, opts)
    };

    if opts.normalize_separated_runs {
        norm = join_separated_runs(norm);
    }
    if opts.normalize_repeated_chars {
        norm = squash_repeated_chars(norm);
    }

    // Single char-index rebuild after all mutating passes.
    norm.rebuild_char_index();
    if build_boundaries {
        norm.boundary_bytes = Some(word_boundary_bytes(&norm.text));
    } else {
        norm.boundary_bytes = None;
    }
    norm
}

fn normalize_ascii(input: &str, opts: NormalizeOptions) -> NormalizedText {
    let bytes = input.as_bytes();
    let mut text = String::with_capacity(bytes.len());
    let mut char_ranges: Vec<(usize, usize)> = Vec::with_capacity(bytes.len());
    let mut pending_sep: Option<(usize, usize)> = None;
    let mut prev_out: Option<char> = None;
    let mut leet_run_end = 0usize;
    let mut leet_run_has_alpha = false;

    for (i, &b) in bytes.iter().enumerate() {
        let ch = b as char;
        let orig_end = i + 1;

        if opts.normalize_leet && i >= leet_run_end {
            if is_leet_token_char(ch, opts.normalize_separated_runs) {
                leet_run_end = bytes[i..]
                    .iter()
                    .position(|&candidate| {
                        !is_leet_token_char(candidate as char, opts.normalize_separated_runs)
                    })
                    .map_or(bytes.len(), |offset| i + offset);
                leet_run_has_alpha = bytes[i..leet_run_end].iter().any(u8::is_ascii_alphabetic);
            } else {
                leet_run_end = i + 1;
                leet_run_has_alpha = false;
            }
        }

        if opts.canonical_separators && is_separator(ch) {
            pending_sep = Some(match pending_sep {
                Some((s, _)) => (s, orig_end),
                None => (i, orig_end),
            });
            continue;
        }

        if let Some((sep_s, sep_e)) = pending_sep.take() {
            if !text.is_empty() {
                push_mapped_char(&mut text, &mut char_ranges, ' ', (sep_s, sep_e));
                prev_out = Some(' ');
            }
        }

        let lc = ch.to_ascii_lowercase();
        let out_ch = if opts.normalize_leet {
            let next_in = bytes
                .get(i + 1)
                .map(|&nb| (nb as char).to_ascii_lowercase());
            fold_leet_char(lc, prev_out, next_in, leet_run_has_alpha)
        } else {
            lc
        };
        push_mapped_char(&mut text, &mut char_ranges, out_ch, (i, orig_end));
        prev_out = Some(out_ch);
    }

    NormalizedText {
        text,
        char_ranges,
        char_norm_starts: Vec::new(),
        boundary_bytes: None,
    }
}

fn normalize_unicode(input: &str, opts: NormalizeOptions) -> NormalizedText {
    // Normalize complete grapheme clusters rather than individual scalars. Canonical
    // composition may cross scalar boundaries (for example `e` + COMBINING ACUTE),
    // while a grapheme is also the smallest useful source range for projection.
    let mut mapped: Vec<(char, (usize, usize))> = Vec::with_capacity(input.chars().count());
    for (byte_idx, cluster) in input.grapheme_indices(true) {
        let orig = (byte_idx, byte_idx + cluster.len());
        mapped.extend(
            cluster
                .nfkc()
                .case_fold()
                .nfkc()
                .map(|normalized| (normalized, orig)),
        );
    }

    let mut text = String::with_capacity(input.len());
    let mut char_ranges: Vec<(usize, usize)> = Vec::with_capacity(mapped.len());
    let mut pending_sep: Option<(usize, usize)> = None;
    let mut prev_out: Option<char> = None;
    let mut leet_run_end = 0usize;
    let mut leet_run_has_alpha = false;

    for (i, &(ch, orig)) in mapped.iter().enumerate() {
        if opts.normalize_leet && i >= leet_run_end {
            if is_leet_token_char(ch, opts.normalize_separated_runs) {
                leet_run_end = mapped[i..]
                    .iter()
                    .position(|(candidate, _)| {
                        !is_leet_token_char(*candidate, opts.normalize_separated_runs)
                    })
                    .map_or(mapped.len(), |offset| i + offset);
                // The built-in substitutions model English/Latin leetspeak. A
                // non-Latin letter in an adjacent UAX#29 segment must not turn a
                // numeric identifier into an English profanity (for example
                // `455中` -> `ass中`). NFKC has already converted fullwidth
                // Latin letters to ASCII here.
                leet_run_has_alpha = mapped[i..leet_run_end]
                    .iter()
                    .any(|(candidate, _)| candidate.is_ascii_alphabetic());
            } else {
                leet_run_end = i + 1;
                leet_run_has_alpha = false;
            }
        }
        if opts.canonical_separators && is_separator(ch) {
            pending_sep = Some(match pending_sep {
                Some((s, _)) => (s, orig.1),
                None => orig,
            });
            continue;
        }

        if let Some((sep_s, sep_e)) = pending_sep.take() {
            if !text.is_empty() {
                push_mapped_char(&mut text, &mut char_ranges, ' ', (sep_s, sep_e));
                prev_out = Some(' ');
            }
        }

        let next_in = mapped.get(i + 1).map(|(next, _)| *next);
        let out_ch = if opts.normalize_leet {
            fold_leet_char(ch, prev_out, next_in, leet_run_has_alpha)
        } else {
            ch
        };
        push_mapped_char(&mut text, &mut char_ranges, out_ch, orig);
        prev_out = Some(out_ch);
    }

    NormalizedText {
        text,
        char_ranges,
        char_norm_starts: Vec::new(),
        boundary_bytes: None,
    }
}

fn squash_repeated_chars(input: NormalizedText) -> NormalizedText {
    let chars: Vec<char> = input.text.chars().collect();
    if chars.is_empty() {
        return input;
    }
    let mut text = String::with_capacity(input.text.len());
    let mut char_ranges = Vec::with_capacity(input.char_ranges.len());

    let mut i = 0usize;
    while i < chars.len() {
        let ch = chars[i];
        let mut j = i + 1;
        while j < chars.len() && chars[j] == ch {
            j += 1;
        }
        let run = j - i;
        if ch.is_alphabetic() && run >= REPEAT_MIN_RUN {
            let orig_start = input.char_ranges[i].0;
            let orig_end = input.char_ranges[j - 1].1;
            push_mapped_char(&mut text, &mut char_ranges, ch, (orig_start, orig_end));
        } else {
            for (ch_k, range) in chars[i..j].iter().zip(input.char_ranges[i..j].iter()) {
                push_mapped_char(&mut text, &mut char_ranges, *ch_k, *range);
            }
        }
        i = j;
    }

    NormalizedText {
        text,
        char_ranges,
        char_norm_starts: Vec::new(),
        boundary_bytes: None,
    }
}

fn join_separated_runs(input: NormalizedText) -> NormalizedText {
    let chars: Vec<char> = input.text.chars().collect();
    if chars.len() < SEPARATED_MIN_CHARS * 2 - 1 {
        return input;
    }

    let mut text = String::with_capacity(input.text.len());
    let mut char_ranges = Vec::with_capacity(input.char_ranges.len());
    let mut i = 0usize;

    while i < chars.len() {
        if let Some(end) = find_separated_run(&chars, i) {
            let mut k = i;
            while k < end {
                push_mapped_char(&mut text, &mut char_ranges, chars[k], input.char_ranges[k]);
                k += 2;
            }
            i = end;
        } else {
            push_mapped_char(&mut text, &mut char_ranges, chars[i], input.char_ranges[i]);
            i += 1;
        }
    }

    NormalizedText {
        text,
        char_ranges,
        char_norm_starts: Vec::new(),
        boundary_bytes: None,
    }
}

fn find_separated_run(chars: &[char], start: usize) -> Option<usize> {
    if start >= chars.len() || !chars[start].is_alphanumeric() {
        return None;
    }
    // Do not extend a preceding word into the run (`say f.u.c.k` must not
    // become `yfuck` once space is a glue separator).
    if start > 0 && chars[start - 1].is_alphanumeric() {
        return None;
    }
    let mut letters = 1usize;
    let mut i = start + 1;
    while i + 1 < chars.len() && is_glue_sep(chars[i]) && chars[i + 1].is_alphanumeric() {
        // Only absorb a singleton letter (followed by glue / end / non-alnum).
        // Prevents `f.u.c.k now` from joining the `n` of `now`.
        let next_letter = i + 1;
        let after = next_letter + 1;
        if after < chars.len() && chars[after].is_alphanumeric() && !is_glue_sep(chars[after]) {
            break;
        }
        letters += 1;
        i += 2;
    }
    if letters >= SEPARATED_MIN_CHARS {
        Some(i)
    } else {
        None
    }
}

fn word_boundary_bytes(text: &str) -> Vec<usize> {
    let mut bounds: Vec<usize> = text.split_word_bound_indices().map(|(o, _)| o).collect();
    if bounds.first().copied() != Some(0) {
        bounds.insert(0, 0);
    }
    if bounds.last().copied() != Some(text.len()) {
        bounds.push(text.len());
    }
    bounds.dedup();
    bounds
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn leet_and_case() {
        let n = normalize("B1tch", NormalizeOptions::default());
        assert_eq!(n.text, "bitch");
        let (s, e) = n.project_bytes(0, n.text.len()).unwrap();
        assert_eq!(&"B1tch"[s..e], "B1tch");
    }

    #[test]
    fn leet_requires_an_alphabetic_token_anchor() {
        let opts = NormalizeOptions::default();
        assert_eq!(normalize("455", opts).text, "455");
        assert_eq!(normalize("80085", opts).text, "80085");
        assert_eq!(
            normalize("order 455 shipped", opts).text,
            "order 455 shipped"
        );
        assert_eq!(normalize("455*item", opts).text, "455*item");
        assert_eq!(normalize("a55", opts).text, "ass");
        assert_eq!(normalize("b１tch", opts).text, "bitch");
        assert_eq!(normalize("@ss", opts).text, "ass");
        assert_eq!(normalize("455中", opts).text, "455中");
        assert_eq!(normalize("中455", opts).text, "中455");
        assert_eq!(normalize("80085ก", opts).text, "80085ก");
    }

    #[test]
    fn leet_bang_to_i_infix_only() {
        assert_eq!(normalize("sh!t", NormalizeOptions::default()).text, "shit");
        assert_eq!(
            normalize("b!tch", NormalizeOptions::default()).text,
            "bitch"
        );
        // Trailing bang must not become a letter (would break `Fuck!` → `fucki`).
        assert_eq!(
            normalize("fuck!", NormalizeOptions::default()).text,
            "fuck!"
        );
    }

    #[test]
    fn whitespace_collapse_for_phrases() {
        let n = normalize("blow   job", NormalizeOptions::default());
        assert_eq!(n.text, "blow job");
    }

    #[test]
    fn nfkc_composes_across_scalar_boundaries() {
        let composed = normalize("é Å ñ", NormalizeOptions::default());
        let decomposed = normalize("e\u{301} A\u{30a} n\u{303}", NormalizeOptions::default());
        assert_eq!(decomposed.text, composed.text);
        let (start, end) = decomposed.project_bytes(0, "é".len()).unwrap();
        assert_eq!(&"e\u{301} A\u{30a} n\u{303}"[start..end], "e\u{301}");
    }

    #[test]
    fn full_case_fold_handles_sharp_s_and_sigma() {
        assert_eq!(
            normalize("Straße", NormalizeOptions::default()).text,
            "strasse"
        );
        assert_eq!(
            normalize("ΟΣ ος οσ", NormalizeOptions::default()).text,
            "οσ οσ οσ"
        );
    }

    #[test]
    fn hyphen_as_separator() {
        let n = normalize("blow-job", NormalizeOptions::default());
        assert_eq!(n.text, "blow job");
    }

    #[test]
    fn project_partial_span() {
        let original = "xx FUCK yy";
        let n = normalize(original, NormalizeOptions::default());
        assert!(n.text.contains("fuck"));
        let start = n.text.find("fuck").unwrap();
        let end = start + 4;
        let (s, e) = n.project_bytes(start, end).unwrap();
        assert_eq!(&original[s..e], "FUCK");
    }

    #[test]
    fn repeated_chars_squash() {
        let opts = NormalizeOptions {
            normalize_repeated_chars: true,
            ..NormalizeOptions::default()
        };
        let n = normalize("fuuuck", opts);
        assert_eq!(n.text, "fuck");
        let (s, e) = n.project_bytes(0, n.text.len()).unwrap();
        assert_eq!(&"fuuuck"[s..e], "fuuuck");
    }

    #[test]
    fn repeated_chars_preserves_doubles() {
        let opts = NormalizeOptions {
            normalize_repeated_chars: true,
            ..NormalizeOptions::default()
        };
        assert_eq!(normalize("book", opts).text, "book");
    }

    #[test]
    fn separated_runs_join() {
        let opts = NormalizeOptions {
            normalize_separated_runs: true,
            ..NormalizeOptions::default()
        };
        let original = "f.u.c.k";
        let n = normalize(original, opts);
        assert_eq!(n.text, "fuck");
        let (s, e) = n.project_bytes(0, n.text.len()).unwrap();
        assert_eq!(&original[s..e], "f.u.c.k");
        // Each kept letter maps to its own original scalar range.
        let start = n.text.find("uck").unwrap();
        let end = start + 3;
        let (os, oe) = n.project_bytes(start, end).unwrap();
        assert_eq!(&original[os..oe], "u.c.k");
    }

    #[test]
    fn separated_runs_join_spaces() {
        let opts = NormalizeOptions {
            normalize_separated_runs: true,
            ..NormalizeOptions::default()
        };
        assert_eq!(normalize("f u c k", opts).text, "fuck");
        assert_eq!(normalize("f  u   c    k", opts).text, "fuck");
        // Mixed glue still joins.
        assert_eq!(normalize("f.u c_k", opts).text, "fuck");
        // Preceding word must not be eaten when space is glue.
        assert_eq!(normalize("say f.u.c.k now", opts).text, "say fuck now");
        assert_eq!(normalize("say f u c k now", opts).text, "say fuck now");
    }

    #[test]
    fn project_empty_span_uses_local_orig() {
        let n = normalize("ab", NormalizeOptions::default());
        let mid = n.char_norm_starts[1];
        let (s, e) = n.project_bytes(mid, mid).unwrap();
        assert_eq!(s, e);
        assert_eq!(s, n.char_ranges[1].0);
        let (s0, e0) = n.project_bytes(0, 0).unwrap();
        assert_eq!((s0, e0), (0, 0));
    }

    #[test]
    fn separated_then_repeated() {
        let opts = NormalizeOptions {
            normalize_separated_runs: true,
            normalize_repeated_chars: true,
            ..NormalizeOptions::default()
        };
        assert_eq!(normalize("f.u.u.u.c.k", opts).text, "fuck");
    }

    #[test]
    fn lazy_boundaries_unbuilt_until_ensure() {
        let mut n = normalize_ex("hello world", NormalizeOptions::default(), false);
        assert!(n.boundary_bytes.is_none());
        n.ensure_boundaries();
        assert!(n.boundary_bytes.is_some());
        assert!(n.is_boundary(0));
        assert!(n.is_boundary(n.text.len()));
    }

    #[test]
    fn project_bytes_covers_full_string_variants() {
        let opts = [
            NormalizeOptions::default(),
            NormalizeOptions {
                normalize_repeated_chars: true,
                ..NormalizeOptions::default()
            },
            NormalizeOptions {
                normalize_separated_runs: true,
                ..NormalizeOptions::default()
            },
        ];
        let samples = [
            "",
            "a",
            "fuck",
            "fuuuck",
            "f.u.c.k",
            "🔥FUCK🔥",
            "please pass",
            "これは",
            "ﬁne",
        ];
        for opt in opts {
            for original in samples {
                let n = normalize(original, opt);
                assert_eq!(n.char_ranges.len() + 1, n.char_norm_starts.len());
                assert_eq!(*n.char_norm_starts.last().unwrap_or(&0), n.text.len());
                assert!(n.boundary_bytes.is_some());
                if n.text.is_empty() {
                    continue;
                }
                let (s, e) = n.project_bytes(0, n.text.len()).unwrap();
                assert!(s <= e && e <= original.len());
                assert!(original.is_char_boundary(s) && original.is_char_boundary(e));
                // Walk every normalized char and ensure projection is in-range.
                let mut byte = 0usize;
                for ch in n.text.chars() {
                    let next = byte + ch.len_utf8();
                    let (os, oe) = n.project_bytes(byte, next).unwrap();
                    assert!(os <= oe && oe <= original.len());
                    byte = next;
                }
            }
        }
    }

    #[test]
    fn robustness_randomish_inputs_do_not_panic() {
        // Deterministic pseudo-random Unicode-ish inputs (no external fuzzer required).
        let mut seed: u64 = 0xC0FFEE;
        let mut next = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            seed
        };
        let opts = NormalizeOptions {
            normalize_repeated_chars: true,
            normalize_separated_runs: true,
            ..NormalizeOptions::default()
        };
        for _ in 0..200 {
            let len = (next() % 48) as usize;
            let mut s = String::new();
            for _ in 0..len {
                let roll = next() % 8;
                let ch = match roll {
                    0 => char::from_u32(0x61 + (next() % 26) as u32).unwrap(), // a-z
                    1 => '.',
                    2 => '*',
                    3 => '_',
                    4 => ' ',
                    5 => '-',
                    6 => char::from_u32(0x1F600 + (next() % 10) as u32).unwrap_or('x'),
                    _ => char::from_u32(0x30 + (next() % 10) as u32).unwrap(),
                };
                s.push(ch);
            }
            let n = normalize(&s, opts);
            assert_eq!(n.char_ranges.len(), n.text.chars().count());
            if !n.text.is_empty() {
                let _ = n.project_bytes(0, n.text.len());
            }
        }
    }
}
