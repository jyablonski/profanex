//! Scan orchestration: normalize → exact/phrase → fuzzy → allowlist → resolve.

use aho_corasick::Match as AcMatch;

use crate::fuzzy::{
    collect_fuzzy_candidates, contains_fuzzy_candidate, FuzzyConfig, FuzzyTokenCache,
};
use crate::lexicon::CompiledLexicon;
use crate::mask::{apply_mask, MaskStyle};
use crate::normalize::{normalize_ex, NormalizedText};
use crate::resolve::{resolve_candidates, CoverRanges, MatchCandidate};

#[derive(Debug, Clone, Copy)]
pub struct ScanConfig {
    pub word_boundaries: bool,
    pub enable_fuzzy: bool,
    pub fuzzy: FuzzyConfig,
}

impl Default for ScanConfig {
    fn default() -> Self {
        Self {
            word_boundaries: true,
            enable_fuzzy: false,
            fuzzy: FuzzyConfig::default(),
        }
    }
}

/// Public match in original UTF-8 byte space.
#[derive(Debug, Clone)]
pub struct ScanMatch {
    pub start: usize,
    pub end: usize,
    pub term: String,
    pub categories: u32,
    pub score: f64,
    pub kind: crate::exact::MatchKind,
}

/// Fuzzy tokenization always needs boundaries; exact/phrase only needs them when WB is on
/// and there is at least one raw AC hit to filter.
fn eager_boundaries(config: ScanConfig) -> bool {
    config.enable_fuzzy
}

/// Prepare boundaries (if needed) and allow spans after we know banned AC work remains.
fn prepare_filters(
    norm: &mut NormalizedText,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
) -> CoverRanges {
    if config.word_boundaries || config.enable_fuzzy {
        norm.ensure_boundaries();
    }
    collect_allow_spans(norm, lexicon, config.word_boundaries)
}

/// Shared scan returning resolved candidates (no term strings yet).
fn scan_resolved(
    text: &str,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    cache: Option<&FuzzyTokenCache>,
) -> Vec<MatchCandidate> {
    if lexicon.is_empty {
        return Vec::new();
    }
    let mut norm = normalize_ex(text, lexicon.normalize, eager_boundaries(config));

    // Banned AC first: clean texts never pay boundary build or allow-span scan.
    let has_raw = lexicon
        .banned_ac
        .find_overlapping_iter(&norm.text)
        .next()
        .is_some();
    if !has_raw && !config.enable_fuzzy {
        return Vec::new();
    }

    let allow_spans = prepare_filters(&mut norm, lexicon, config);
    let mut candidates = Vec::new();
    if has_raw {
        for mat in lexicon.banned_ac.find_overlapping_iter(&norm.text) {
            if let Some(c) = candidate_ok(text, &norm, lexicon, config, &allow_spans, &mat) {
                candidates.push(c);
            }
        }
    }
    if config.enable_fuzzy {
        let fuzzy = collect_fuzzy_candidates(
            text,
            &norm,
            lexicon,
            config.word_boundaries,
            config.fuzzy,
            &candidates,
            &allow_spans,
            cache,
        );
        candidates.extend(fuzzy);
    }
    resolve_candidates(candidates)
}

fn to_scan_matches(resolved: Vec<MatchCandidate>, lexicon: &CompiledLexicon) -> Vec<ScanMatch> {
    resolved
        .into_iter()
        .map(|c| {
            let meta = &lexicon.banned_meta[c.pattern_id];
            ScanMatch {
                start: c.orig_start,
                end: c.orig_end,
                term: meta.term.clone(),
                categories: c.categories,
                score: c.score,
                kind: c.kind,
            }
        })
        .collect()
}

/// Find deterministic non-overlapping matches in `text`.
pub fn find_matches(
    text: &str,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    cache: Option<&FuzzyTokenCache>,
) -> Vec<ScanMatch> {
    to_scan_matches(scan_resolved(text, lexicon, config, cache), lexicon)
}

/// True if at least one policy-accepted candidate exists.
///
/// Early-exits on the first exact/phrase hit (including when fuzzy is enabled —
/// presence is known without collecting further exact hits or running fuzzy).
/// Runs fuzzy only when no exact/phrase candidate survives filtering.
pub fn contains(
    text: &str,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    cache: Option<&FuzzyTokenCache>,
) -> bool {
    if lexicon.is_empty {
        return false;
    }
    let mut norm = normalize_ex(text, lexicon.normalize, eager_boundaries(config));

    // Probe first so clean texts retain the no-boundary/no-allow fast path. If a
    // raw hit exists, rescan after preparing filters and stop at the first accepted
    // candidate instead of allocating every overlapping hit.
    let has_raw = lexicon
        .banned_ac
        .find_overlapping_iter(&norm.text)
        .next()
        .is_some();

    if !has_raw {
        if !config.enable_fuzzy {
            return false;
        }
        let allow_spans = prepare_filters(&mut norm, lexicon, config);
        return contains_fuzzy_candidate(
            text,
            &norm,
            lexicon,
            config.word_boundaries,
            config.fuzzy,
            &[],
            &allow_spans,
            cache,
        );
    }

    let allow_spans = prepare_filters(&mut norm, lexicon, config);
    for mat in lexicon.banned_ac.find_overlapping_iter(&norm.text) {
        if candidate_ok(text, &norm, lexicon, config, &allow_spans, &mat).is_some() {
            return true;
        }
    }
    if !config.enable_fuzzy {
        return false;
    }
    contains_fuzzy_candidate(
        text,
        &norm,
        lexicon,
        config.word_boundaries,
        config.fuzzy,
        &[],
        &allow_spans,
        cache,
    )
}

/// Mask using the same spans as `find_matches`.
pub fn clean(
    text: &str,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    style: MaskStyle,
    cache: Option<&FuzzyTokenCache>,
) -> String {
    let resolved = scan_resolved(text, lexicon, config, cache);
    apply_mask(text, &resolved, style)
}

/// Return the detection flag and cleaned text from one resolved scan.
pub fn analyze(
    text: &str,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    style: MaskStyle,
    cache: Option<&FuzzyTokenCache>,
) -> (bool, String) {
    let resolved = scan_resolved(text, lexicon, config, cache);
    let contains = !resolved.is_empty();
    (contains, apply_mask(text, &resolved, style))
}

fn candidate_ok(
    original: &str,
    norm: &NormalizedText,
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    allow_spans: &CoverRanges,
    mat: &AcMatch,
) -> Option<MatchCandidate> {
    let ns = mat.start();
    let ne = mat.end();
    if config.word_boundaries && !(norm.is_boundary(ns) && norm.is_boundary(ne)) {
        return None;
    }
    if allow_spans.covers(ns, ne) {
        return None;
    }
    let (os, oe) = norm.project_bytes(ns, ne)?;
    if oe > original.len() || os > oe {
        return None;
    }
    if !original.is_char_boundary(os) || !original.is_char_boundary(oe) {
        return None;
    }
    let pattern_id = mat.pattern().as_usize();
    let meta = &lexicon.banned_meta[pattern_id];
    Some(MatchCandidate {
        orig_start: os,
        orig_end: oe,
        norm_start: ns,
        norm_end: ne,
        pattern_id,
        categories: meta.categories,
        score: 100.0,
        kind: meta.kind,
    })
}

fn collect_allow_spans(
    norm: &NormalizedText,
    lexicon: &CompiledLexicon,
    word_boundaries: bool,
) -> CoverRanges {
    let Some(ac) = &lexicon.allow_ac else {
        return CoverRanges::default();
    };
    CoverRanges::new(
        ac.find_overlapping_iter(&norm.text)
            .filter(|m| {
                !word_boundaries || (norm.is_boundary(m.start()) && norm.is_boundary(m.end()))
            })
            .map(|m| (m.start(), m.end()))
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fuzzy::FuzzyConfig;
    use crate::lexicon::LexiconTerm;
    use crate::normalize::NormalizeOptions;
    use crate::test_lexicon;

    fn eng(words: &[&str]) -> CompiledLexicon {
        test_lexicon(words, &[])
    }

    #[test]
    fn finds_exact_and_projects() {
        let lex = eng(&["fuck"]);
        let ms = find_matches("what the fuck", &lex, ScanConfig::default(), None);
        assert_eq!(ms.len(), 1);
        assert_eq!(&"what the fuck"[ms[0].start..ms[0].end], "fuck");
        assert_eq!(ms[0].term, "fuck");
    }

    #[test]
    fn contains_matches_find() {
        let lex = eng(&["fuck", "ass", "asshole"]);
        for text in ["clean", "fuck", "asshole", "what the fuck"] {
            assert_eq!(
                contains(text, &lex, ScanConfig::default(), None),
                !find_matches(text, &lex, ScanConfig::default(), None).is_empty()
            );
        }
    }

    #[test]
    fn respects_word_boundaries() {
        let lex = eng(&["ass"]);
        assert!(find_matches("classic", &lex, ScanConfig::default(), None).is_empty());
        assert!(!find_matches(
            "classic",
            &lex,
            ScanConfig {
                word_boundaries: false,
                ..ScanConfig::default()
            },
            None,
        )
        .is_empty());
    }

    #[test]
    fn phrase_match() {
        let lex = eng(&["blow job"]);
        let ms = find_matches("a blow job here", &lex, ScanConfig::default(), None);
        assert_eq!(ms.len(), 1);
        assert_eq!(&"a blow job here"[ms[0].start..ms[0].end], "blow job");
    }

    #[test]
    fn normalized_allowlist_entry_overrides_banned_entry() {
        let terms = [LexiconTerm {
            term: "pass".into(),
            pattern: "pass".into(),
            categories: 1,
        }];
        let lexicon =
            CompiledLexicon::compile(&terms, &["PASS".into()], NormalizeOptions::default())
                .expect("allowlist override compiles");
        assert!(!contains("pass", &lexicon, ScanConfig::default(), None));
        assert!(find_matches("pass", &lexicon, ScanConfig::default(), None).is_empty());
    }

    #[test]
    fn fuzzy_finds_typo() {
        let lex = eng(&["fuck"]);
        let cfg = ScanConfig {
            enable_fuzzy: true,
            fuzzy: FuzzyConfig {
                threshold: 75.0,
                min_fuzzy_len: 4,
                ..FuzzyConfig::default()
            },
            ..ScanConfig::default()
        };
        let ms = find_matches("what the fukc", &lex, cfg, None);
        assert_eq!(ms.len(), 1);
        assert_eq!(ms[0].kind, crate::exact::MatchKind::Fuzzy);
        assert_eq!(ms[0].term, "fuck");
        assert!(ms[0].score >= 75.0);
        assert!(contains("what the fukc", &lex, cfg, None));
    }

    #[test]
    fn fuzzy_skips_short_terms() {
        let lex = eng(&["ass"]);
        let cfg = ScanConfig {
            enable_fuzzy: true,
            fuzzy: FuzzyConfig {
                threshold: 50.0,
                min_fuzzy_len: 4,
                ..FuzzyConfig::default()
            },
            ..ScanConfig::default()
        };
        // "asx" is length 3; "ass" is below min_fuzzy_len for fuzzy buckets usage
        assert!(find_matches("asx", &lex, cfg, None).is_empty());
    }

    #[test]
    fn contains_with_fuzzy_skips_fuzzy_after_exact_hit() {
        let lex = eng(&["fuck", "shit"]);
        let cfg = ScanConfig {
            enable_fuzzy: true,
            fuzzy: FuzzyConfig {
                threshold: 75.0,
                ..FuzzyConfig::default()
            },
            ..ScanConfig::default()
        };
        // Exact hit present; contains must still be true (and should not require fuzzy).
        assert!(contains("what the fuck and fukc", &lex, cfg, None));
        assert!(contains("only typo fukc here", &lex, cfg, None));
    }

    #[test]
    fn fuzzy_identical_token_is_exact_not_fuzzy() {
        // Equal-length tight-threshold fuzzy bucket is dead: identical tokens are
        // exact AC hits (and allow-covered the same way). Regression for P2-9.
        let lex = eng(&["fuck"]);
        let cfg = ScanConfig {
            enable_fuzzy: true,
            fuzzy: FuzzyConfig {
                threshold: 85.0,
                ..FuzzyConfig::default()
            },
            ..ScanConfig::default()
        };
        let ms = find_matches("fuck", &lex, cfg, None);
        assert_eq!(ms.len(), 1);
        assert_eq!(ms[0].kind, crate::exact::MatchKind::Exact);

        let no_wb = ScanConfig {
            word_boundaries: false,
            ..cfg
        };
        let ms2 = find_matches("xxfuckyy", &lex, no_wb, None);
        assert!(!ms2.is_empty());
        assert!(ms2.iter().all(|m| m.kind == crate::exact::MatchKind::Exact));

        let lex_allow = test_lexicon(&["ass"], &["pass"]);
        assert!(find_matches("please pass", &lex_allow, cfg, None).is_empty());
    }

    #[test]
    fn fuzzy_cache_does_not_change_results() {
        let lex = eng(&["fuck"]);
        let cfg = ScanConfig {
            enable_fuzzy: true,
            fuzzy: FuzzyConfig {
                threshold: 75.0,
                ..FuzzyConfig::default()
            },
            ..ScanConfig::default()
        };
        let cache = FuzzyTokenCache::new(64);
        let texts = ["fukc", "hello", "fukc again", "what the fukc"];
        for text in texts {
            let a = find_matches(text, &lex, cfg, None);
            let b = find_matches(text, &lex, cfg, Some(&cache));
            assert_eq!(a.len(), b.len());
            for (ma, mb) in a.iter().zip(b.iter()) {
                assert_eq!(ma.start, mb.start);
                assert_eq!(ma.end, mb.end);
                assert_eq!(ma.term, mb.term);
                assert_eq!(ma.score, mb.score);
            }
        }
    }

    #[test]
    fn separated_run_partial_match_does_not_inflate_span() {
        let terms = [LexiconTerm {
            term: "uck".into(),
            pattern: "uck".into(),
            categories: 1,
        }];
        let lex = CompiledLexicon::compile(
            &terms,
            &[],
            NormalizeOptions {
                normalize_separated_runs: true,
                ..NormalizeOptions::default()
            },
        )
        .unwrap();
        let cfg = ScanConfig {
            word_boundaries: false,
            ..ScanConfig::default()
        };
        let original = "f.u.c.k";
        let ms = find_matches(original, &lex, cfg, None);
        assert_eq!(ms.len(), 1);
        assert_eq!(&original[ms[0].start..ms[0].end], "u.c.k");
        assert_eq!(
            clean(original, &lex, cfg, MaskStyle::Stars, None),
            "f.*****"
        );
    }

    #[test]
    fn allowlist_respects_word_boundaries() {
        let lex = test_lexicon(&["ass"], &["pass"]);
        let with_wb = ScanConfig::default();
        assert!(find_matches("please pass", &lex, with_wb, None).is_empty());
        assert!(find_matches("password", &lex, with_wb, None).is_empty());

        let no_wb = ScanConfig {
            word_boundaries: false,
            ..ScanConfig::default()
        };
        // Substring allow still shields when word boundaries are off.
        assert!(find_matches("password", &lex, no_wb, None).is_empty());
        // Without an allow hit, substring banned matches.
        let lex_no_allow = eng(&["ass"]);
        assert!(!find_matches("password", &lex_no_allow, no_wb, None).is_empty());
    }

    #[test]
    fn contains_equals_find_with_fuzzy_and_allow() {
        let lex = test_lexicon(&["fuck", "ass"], &["classic"]);
        let cfgs = [
            ScanConfig::default(),
            ScanConfig {
                enable_fuzzy: true,
                fuzzy: FuzzyConfig {
                    threshold: 75.0,
                    ..FuzzyConfig::default()
                },
                ..ScanConfig::default()
            },
            ScanConfig {
                word_boundaries: false,
                enable_fuzzy: true,
                fuzzy: FuzzyConfig {
                    threshold: 75.0,
                    ..FuzzyConfig::default()
                },
            },
        ];
        let texts = [
            "clean text here",
            "what the fuck",
            "classic",
            "fukc typo",
            "password",
            "",
        ];
        for cfg in cfgs {
            for text in texts {
                assert_eq!(
                    contains(text, &lex, cfg, None),
                    !find_matches(text, &lex, cfg, None).is_empty(),
                    "mismatch on {text:?} cfg={cfg:?}"
                );
            }
        }
    }
}
