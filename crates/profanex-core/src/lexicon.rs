//! Lexicon compilation into Aho-Corasick automata and fuzzy length buckets.

use std::collections::BTreeMap;

use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind as AcMatchKind};
use thiserror::Error;

use crate::normalize::{normalize, NormalizeOptions};

#[derive(Debug, Error)]
pub enum LexiconError {
    #[error("empty banned term")]
    EmptyTerm,
    #[error("failed to build automaton: {0}")]
    Automaton(String),
}

/// One banned lexicon entry prior to compile.
#[derive(Debug, Clone)]
pub struct LexiconTerm {
    /// Deterministic canonical term reported in matches.
    pub term: String,
    /// Pattern text to normalize and search for.
    pub pattern: String,
    /// Category bitflags.
    pub categories: u32,
}

#[derive(Debug, Clone)]
pub struct PatternMeta {
    pub term: String,
    pub categories: u32,
    pub kind: crate::exact::MatchKind,
    /// Normalized pattern text (for fuzzy comparisons).
    pub norm_pattern: String,
    /// Precomputed scalars of `norm_pattern` (avoids re-collecting in DP).
    pub norm_pattern_chars: Box<[char]>,
    /// Unicode scalar length of `norm_pattern`.
    pub norm_char_len: usize,
    /// Character-presence bitmask for indel lower-bound prefilter (26 letters + digit/other).
    pub char_mask: u32,
}

struct PendingPattern {
    term: String,
    categories: u32,
    kind: crate::exact::MatchKind,
    norm_pattern: String,
    norm_char_len: usize,
}

/// Pack letter / digit / other presence into a `u32` for fuzzy prefiltering.
pub(crate) fn char_presence_mask(chars: &[char]) -> u32 {
    let mut mask = 0u32;
    for &ch in chars {
        let bit = if ch.is_ascii_alphabetic() {
            (ch.to_ascii_lowercase() as u8 - b'a') as u32
        } else if ch.is_ascii_digit() {
            26
        } else {
            27
        };
        mask |= 1u32 << bit;
    }
    mask
}

fn term_rank<'a>(term: &'a str, norm_pattern: &str) -> (u8, &'a str) {
    let plain = if term == norm_pattern { 0 } else { 1 };
    (plain, term)
}

fn build_ac(patterns: &[String]) -> Result<AhoCorasick, LexiconError> {
    AhoCorasickBuilder::new()
        .match_kind(AcMatchKind::Standard)
        .build(patterns)
        .map_err(|e| LexiconError::Automaton(e.to_string()))
}

/// Compiled banned + allowlist automata.
pub struct CompiledLexicon {
    pub banned_ac: AhoCorasick,
    pub banned_meta: Vec<PatternMeta>,
    pub allow_ac: Option<AhoCorasick>,
    /// Single-token patterns eligible for fuzzy, keyed by Unicode scalar length.
    pub fuzzy_buckets: BTreeMap<usize, Vec<usize>>,
    pub normalize: NormalizeOptions,
    pub is_empty: bool,
}

impl CompiledLexicon {
    pub fn compile(
        terms: &[LexiconTerm],
        allowlist: &[String],
        normalize_opts: NormalizeOptions,
    ) -> Result<Self, LexiconError> {
        let mut by_norm: BTreeMap<String, PendingPattern> = BTreeMap::new();

        for t in terms {
            if t.pattern.trim().is_empty() || t.term.trim().is_empty() {
                return Err(LexiconError::EmptyTerm);
            }
            let norm = normalize(&t.pattern, normalize_opts);
            if norm.text.is_empty() {
                return Err(LexiconError::EmptyTerm);
            }
            let kind = if norm.text.contains(' ') {
                crate::exact::MatchKind::Phrase
            } else {
                crate::exact::MatchKind::Exact
            };
            let norm_char_len = norm.text.chars().count();

            match by_norm.get_mut(&norm.text) {
                Some(existing) => {
                    existing.categories |= t.categories;
                    if term_rank(&t.term, &norm.text) < term_rank(&existing.term, &norm.text) {
                        existing.term = t.term.clone();
                    }
                }
                None => {
                    by_norm.insert(
                        norm.text.clone(),
                        PendingPattern {
                            term: t.term.clone(),
                            categories: t.categories,
                            kind,
                            norm_pattern: norm.text.clone(),
                            norm_char_len,
                        },
                    );
                }
            }
        }

        let allow_norm: BTreeMap<String, ()> = allowlist
            .iter()
            .map(|p| normalize(p, normalize_opts).text)
            .filter(|t| !t.is_empty())
            .map(|t| (t, ()))
            .collect();

        let mut patterns: Vec<String> = Vec::with_capacity(by_norm.len());
        let mut meta: Vec<PatternMeta> = Vec::with_capacity(by_norm.len());
        let mut fuzzy_buckets: BTreeMap<usize, Vec<usize>> = BTreeMap::new();

        for (pattern, pending) in by_norm {
            let pattern_id = meta.len();
            // Single-token only for fuzzy buckets (phrases excluded).
            if !pending.norm_pattern.contains(' ') {
                fuzzy_buckets
                    .entry(pending.norm_char_len)
                    .or_default()
                    .push(pattern_id);
            }
            let norm_pattern_chars: Box<[char]> = pending.norm_pattern.chars().collect();
            let char_mask = char_presence_mask(&norm_pattern_chars);
            patterns.push(pattern);
            meta.push(PatternMeta {
                term: pending.term,
                categories: pending.categories,
                kind: pending.kind,
                norm_pattern: pending.norm_pattern,
                norm_pattern_chars,
                norm_char_len: pending.norm_char_len,
                char_mask,
            });
        }

        let is_empty = patterns.is_empty();
        let banned_ac = build_ac(&patterns)?;

        let allow_ac = if allow_norm.is_empty() {
            None
        } else {
            let allow_patterns: Vec<String> = allow_norm.into_keys().collect();
            Some(build_ac(&allow_patterns)?)
        };

        Ok(Self {
            banned_ac,
            banned_meta: meta,
            allow_ac,
            fuzzy_buckets,
            normalize: normalize_opts,
            is_empty,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::normalize::NormalizeOptions;

    #[test]
    fn rejects_empty_terms() {
        let opts = NormalizeOptions::default();
        let empty = LexiconTerm {
            term: " ".into(),
            pattern: " ".into(),
            categories: 1,
        };
        assert!(matches!(
            CompiledLexicon::compile(&[empty], &[], opts),
            Err(LexiconError::EmptyTerm)
        ));
    }

    #[test]
    fn merges_duplicate_normalized_patterns() {
        let opts = NormalizeOptions::default();
        let terms = [
            LexiconTerm {
                term: "fuk".into(),
                pattern: "fuk".into(),
                categories: 1,
            },
            LexiconTerm {
                // Same normalized form as "fuck" under leet? Actually f*ck vs fuck
                term: "fuck".into(),
                pattern: "fuck".into(),
                categories: 2,
            },
            LexiconTerm {
                // Identical norm to fuck via leet: f0ck? 0→o not u. Use "fúck" NFKC?
                // Simpler: same pattern twice with different categories.
                term: "fuck".into(),
                pattern: "fuck".into(),
                categories: 4,
            },
        ];
        let lex = CompiledLexicon::compile(&terms, &[], opts).unwrap();
        assert_eq!(lex.banned_meta.len(), 2);
        let fuck = lex
            .banned_meta
            .iter()
            .find(|m| m.term == "fuck")
            .expect("fuck");
        assert_eq!(fuck.categories, 2 | 4);
    }

    #[test]
    fn prefers_plain_canonical_term_on_norm_collision() {
        let opts = NormalizeOptions {
            normalize_leet: true,
            ..NormalizeOptions::default()
        };
        // "b1tch" and "bitch" normalize to the same form with leet on.
        let terms = [
            LexiconTerm {
                term: "b1tch".into(),
                pattern: "b1tch".into(),
                categories: 1,
            },
            LexiconTerm {
                term: "bitch".into(),
                pattern: "bitch".into(),
                categories: 2,
            },
        ];
        let lex = CompiledLexicon::compile(&terms, &[], opts).unwrap();
        assert_eq!(lex.banned_meta.len(), 1);
        assert_eq!(lex.banned_meta[0].term, "bitch");
        assert_eq!(lex.banned_meta[0].categories, 1 | 2);
    }

    #[test]
    fn empty_banned_with_allowlist() {
        let opts = NormalizeOptions::default();
        let lex = CompiledLexicon::compile(&[], &["safe".into()], opts).unwrap();
        assert!(lex.is_empty);
        assert!(lex.allow_ac.is_some());
    }
}
