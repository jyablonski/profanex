//! Pure Rust matching engine for Profanex.

pub mod batch;
mod exact;
mod fuzzy;
mod lexicon;
mod mask;
mod normalize;
mod resolve;
pub mod scan;

pub use batch::{
    analyze_many, clean_many, contains_many, find_many, validate_batch_options, BatchError,
    BatchOptions,
};
pub use exact::MatchKind;
pub use fuzzy::{
    FuzzyConfig, FuzzyTokenCache, DEFAULT_FUZZY_CACHE_CAP, DEFAULT_LENGTH_DELTA,
    DEFAULT_MAX_FUZZY_TOKEN_LEN, MAX_FUZZY_LENGTH_DELTA, MAX_FUZZY_TOKEN_LEN,
};
pub use lexicon::{CompiledLexicon, LexiconError, LexiconTerm};
pub use mask::{apply_mask, mask_stars, mask_vowels, MaskStyle};
pub use normalize::{normalize, normalize_ex, NormalizeOptions, NormalizedText};
pub use resolve::MatchCandidate;
pub use scan::{analyze, clean, contains, find_matches, ScanConfig, ScanMatch};

/// Category bitflags aligned with the Python `Category` enum order.
pub mod category {
    pub const GENERAL: u32 = 1 << 0;
    pub const SEXUAL: u32 = 1 << 1;
    pub const EXCRETORY: u32 = 1 << 2;
    pub const SLURS: u32 = 1 << 3;
    pub const VIOLENCE: u32 = 1 << 4;
    pub const ALL: u32 = GENERAL | SEXUAL | EXCRETORY | SLURS | VIOLENCE;
}

/// Shared compile helper for unit tests.
#[cfg(test)]
pub(crate) fn test_lexicon(words: &[&str], allow: &[&str]) -> CompiledLexicon {
    let terms: Vec<LexiconTerm> = words
        .iter()
        .map(|w| LexiconTerm {
            term: (*w).to_string(),
            pattern: (*w).to_string(),
            categories: 1,
        })
        .collect();
    let allow_owned: Vec<String> = allow.iter().map(|s| (*s).to_string()).collect();
    CompiledLexicon::compile(
        &terms,
        &allow_owned,
        crate::normalize::NormalizeOptions::default(),
    )
    .expect("test lexicon")
}
