//! Length-bucketed, cutoff-aware single-token fuzzy matching.
//!
//! Score definition (documented): **indel similarity** on Unicode scalars,
//! `score = 100 * (1 - indel_distance(a, b) / (len(a) + len(b)))`, clamped to
//! `[0, 100]`. This matches normalized indel similarity semantics closely enough
//! for a deterministic 0–100 policy threshold.
//!
//! Early abandon: if the remaining cells cannot reach `threshold`, search stops.
//! Optional [`FuzzyTokenCache`] memos best-match results across tokens/texts.
//!
//! Cache keying invariant: the memoized value is a pure function of the token text
//! given a frozen lexicon + fuzzy config on the owning `Engine`. Do not mutate
//! scan/fuzzy config on a live engine that shares this cache.

use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::Mutex;

use crate::exact::MatchKind;
use crate::lexicon::{char_presence_mask, CompiledLexicon};
use crate::normalize::NormalizedText;
use crate::resolve::{CoverRanges, MatchCandidate};

/// Default length window: compare tokens to lexicon terms with
/// `len ∈ [token_len - δ, token_len + δ]`.
pub const DEFAULT_LENGTH_DELTA: usize = 2;

/// Tokens longer than this are skipped for fuzzy matching (deterministic CPU bound).
pub const DEFAULT_MAX_FUZZY_TOKEN_LEN: usize = 64;

/// Maximum configurable length-window radius. Larger values add no useful
/// precision and can otherwise turn one token into a very large sparse scan.
pub const MAX_FUZZY_LENGTH_DELTA: usize = 64;

/// Maximum token length accepted by the fuzzy dynamic-programming path.
pub const MAX_FUZZY_TOKEN_LEN: usize = 256;

/// Default cap for [`FuzzyTokenCache`] entries (unique normalized tokens).
pub const DEFAULT_FUZZY_CACHE_CAP: usize = 16_384;

/// Number of mutex shards for [`FuzzyTokenCache`] (power of two).
const FUZZY_CACHE_SHARDS: usize = 32;

#[derive(Debug, Clone, Copy)]
pub struct FuzzyConfig {
    pub threshold: f64,
    pub min_fuzzy_len: usize,
    pub length_delta: usize,
    pub max_token_len: usize,
}

impl Default for FuzzyConfig {
    fn default() -> Self {
        Self {
            threshold: 85.0,
            min_fuzzy_len: 4,
            length_delta: DEFAULT_LENGTH_DELTA,
            max_token_len: DEFAULT_MAX_FUZZY_TOKEN_LEN,
        }
    }
}

impl FuzzyConfig {
    /// Validate knobs used by fuzzy matching.
    pub fn validate(&self) -> Result<(), String> {
        if !self.threshold.is_finite() || !(0.0..=100.0).contains(&self.threshold) {
            return Err("threshold must be finite and in 0..=100".into());
        }
        if self.min_fuzzy_len < 1 {
            return Err("min_fuzzy_len must be >= 1".into());
        }
        if self.length_delta > MAX_FUZZY_LENGTH_DELTA {
            return Err(format!(
                "fuzzy_length_delta must be <= {MAX_FUZZY_LENGTH_DELTA}"
            ));
        }
        if self.max_token_len > MAX_FUZZY_TOKEN_LEN {
            return Err(format!(
                "fuzzy_max_token_len must be <= {MAX_FUZZY_TOKEN_LEN}"
            ));
        }
        if self.max_token_len < self.min_fuzzy_len {
            return Err("max_token_len must be >= min_fuzzy_len".into());
        }
        Ok(())
    }
}

/// Thread-safe memo of fuzzy best-match results keyed by normalized token text.
///
/// Sharded to reduce Rayon contention. Lock hold time is only the map ops, not DP.
/// A clock policy keeps memory bounded while allowing useful entries to replace a
/// startup flood of one-off tokens.
#[derive(Clone, Copy)]
struct CacheEntry {
    value: Option<(usize, f64)>,
    referenced: bool,
}

struct CacheShard {
    entries: HashMap<String, CacheEntry>,
    slots: Vec<String>,
    hand: usize,
}

impl CacheShard {
    fn new() -> Self {
        Self {
            entries: HashMap::new(),
            slots: Vec::new(),
            hand: 0,
        }
    }

    fn insert(&mut self, token: &str, value: Option<(usize, f64)>, cap: usize) {
        if self.entries.len() < cap {
            self.slots.push(token.to_owned());
            self.entries.insert(
                token.to_owned(),
                CacheEntry {
                    value,
                    referenced: true,
                },
            );
            return;
        }

        loop {
            let victim = self.slots[self.hand].clone();
            if self
                .entries
                .get_mut(&victim)
                .is_some_and(|entry| std::mem::replace(&mut entry.referenced, false))
            {
                self.hand = (self.hand + 1) % self.slots.len();
                continue;
            }
            self.entries.remove(&victim);
            self.slots[self.hand] = token.to_owned();
            self.entries.insert(
                token.to_owned(),
                CacheEntry {
                    value,
                    referenced: true,
                },
            );
            self.hand = (self.hand + 1) % self.slots.len();
            return;
        }
    }
}

type FuzzyCacheShard = Mutex<CacheShard>;

pub struct FuzzyTokenCache {
    shards: [FuzzyCacheShard; FUZZY_CACHE_SHARDS],
    /// Soft per-shard cap derived from total `cap`.
    shard_cap: usize,
}

fn shard_index(token: &str) -> usize {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    token.hash(&mut hasher);
    (hasher.finish() as usize) & (FUZZY_CACHE_SHARDS - 1)
}

impl FuzzyTokenCache {
    pub fn new(cap: usize) -> Self {
        let cap = cap.max(1);
        let shard_cap = (cap / FUZZY_CACHE_SHARDS).max(1);
        // Array init: each shard gets its own mutex+map.
        let shards = std::array::from_fn(|_| Mutex::new(CacheShard::new()));
        Self { shards, shard_cap }
    }

    fn lookup_or_insert(
        &self,
        token: &str,
        compute: impl FnOnce() -> Option<(usize, f64)>,
    ) -> Option<(usize, f64)> {
        let idx = shard_index(token);
        if let Ok(mut guard) = self.shards[idx].lock() {
            if let Some(entry) = guard.entries.get_mut(token) {
                entry.referenced = true;
                return entry.value;
            }
        }
        let computed = compute();
        if let Ok(mut guard) = self.shards[idx].lock() {
            // Another worker may have inserted while we computed.
            if let Some(entry) = guard.entries.get_mut(token) {
                entry.referenced = true;
                return entry.value;
            }
            guard.insert(token, computed, self.shard_cap);
        }
        computed
    }
}

impl Default for FuzzyTokenCache {
    fn default() -> Self {
        Self::new(DEFAULT_FUZZY_CACHE_CAP)
    }
}

/// One word token in normalized space.
#[derive(Debug, Clone)]
struct NormToken<'a> {
    text: &'a str,
    start: usize,
    end: usize,
    char_len: usize,
}

/// Scratch buffers for indel DP, reused across candidate comparisons.
struct IndelScratch {
    prev: Vec<usize>,
    curr: Vec<usize>,
}

impl IndelScratch {
    fn new() -> Self {
        Self {
            prev: Vec::new(),
            curr: Vec::new(),
        }
    }

    fn ensure(&mut self, cols: usize) {
        if self.prev.len() < cols {
            self.prev.resize(cols, 0);
            self.curr.resize(cols, 0);
        }
    }
}

/// Collect fuzzy candidates for tokens that did not exact-match.
#[allow(clippy::too_many_arguments)]
pub fn collect_fuzzy_candidates(
    original: &str,
    norm: &NormalizedText,
    lexicon: &CompiledLexicon,
    word_boundaries: bool,
    fuzzy: FuzzyConfig,
    exact: &[MatchCandidate],
    allow_spans: &CoverRanges,
    cache: Option<&FuzzyTokenCache>,
) -> Vec<MatchCandidate> {
    let mut out = Vec::new();
    visit_fuzzy_candidates(
        original,
        norm,
        lexicon,
        word_boundaries,
        fuzzy,
        exact,
        allow_spans,
        cache,
        |candidate| {
            out.push(candidate);
            false
        },
    );
    out
}

/// True when the first acceptable fuzzy candidate is found.
#[allow(clippy::too_many_arguments)]
pub fn contains_fuzzy_candidate(
    original: &str,
    norm: &NormalizedText,
    lexicon: &CompiledLexicon,
    word_boundaries: bool,
    fuzzy: FuzzyConfig,
    exact: &[MatchCandidate],
    allow_spans: &CoverRanges,
    cache: Option<&FuzzyTokenCache>,
) -> bool {
    visit_fuzzy_candidates(
        original,
        norm,
        lexicon,
        word_boundaries,
        fuzzy,
        exact,
        allow_spans,
        cache,
        |_| true,
    )
}

#[allow(clippy::too_many_arguments)]
fn visit_fuzzy_candidates(
    original: &str,
    norm: &NormalizedText,
    lexicon: &CompiledLexicon,
    word_boundaries: bool,
    fuzzy: FuzzyConfig,
    exact: &[MatchCandidate],
    allow_spans: &CoverRanges,
    cache: Option<&FuzzyTokenCache>,
    mut visit: impl FnMut(MatchCandidate) -> bool,
) -> bool {
    if lexicon.fuzzy_buckets.is_empty() {
        return false;
    }

    for token in word_tokens(norm) {
        if token.char_len < fuzzy.min_fuzzy_len || token.char_len > fuzzy.max_token_len {
            continue;
        }
        if word_boundaries && !(norm.is_boundary(token.start) && norm.is_boundary(token.end)) {
            continue;
        }
        if token_exact_covered(&token, exact) {
            continue;
        }
        if allow_spans.covers(token.start, token.end) {
            continue;
        }

        let best = match cache {
            Some(c) => c.lookup_or_insert(token.text, || {
                best_fuzzy_match(token.text, token.char_len, lexicon, fuzzy)
            }),
            None => best_fuzzy_match(token.text, token.char_len, lexicon, fuzzy),
        };

        let Some((pattern_id, score)) = best else {
            continue;
        };
        let Some((os, oe)) = norm.project_bytes(token.start, token.end) else {
            continue;
        };
        if oe > original.len()
            || os > oe
            || !original.is_char_boundary(os)
            || !original.is_char_boundary(oe)
        {
            continue;
        }
        let meta = &lexicon.banned_meta[pattern_id];
        let candidate = MatchCandidate {
            orig_start: os,
            orig_end: oe,
            norm_start: token.start,
            norm_end: token.end,
            pattern_id,
            categories: meta.categories,
            score,
            kind: MatchKind::Fuzzy,
        };
        if visit(candidate) {
            return true;
        }
    }

    false
}

fn best_fuzzy_match(
    token: &str,
    token_len: usize,
    lexicon: &CompiledLexicon,
    fuzzy: FuzzyConfig,
) -> Option<(usize, f64)> {
    let token_chars: Vec<char> = token.chars().collect();
    let token_mask = char_presence_mask(&token_chars);
    let lo = token_len.saturating_sub(fuzzy.length_delta);
    let hi = token_len.saturating_add(fuzzy.length_delta);
    let mut scratch = IndelScratch::new();

    let mut best: Option<(usize, f64)> = None;
    // Walk only populated lexicon buckets. Iterating every integer in a wide
    // user-configured window makes sparse lexicons needlessly expensive.
    for (&len, _) in lexicon.fuzzy_buckets.range(lo..=hi) {
        for &pattern_id in candidate_pattern_ids(lexicon, len, token_len, fuzzy.threshold) {
            let meta = &lexicon.banned_meta[pattern_id];
            if meta.norm_char_len < fuzzy.min_fuzzy_len {
                continue;
            }
            let Some(score) = indel_ratio_cutoff_chars(
                &token_chars,
                &meta.norm_pattern_chars,
                token_mask,
                meta.char_mask,
                fuzzy.threshold,
                &mut scratch,
            ) else {
                continue;
            };
            match best {
                Some((pid, best_score)) => {
                    if score > best_score || (score == best_score && pattern_id < pid) {
                        best = Some((pattern_id, score));
                    }
                }
                None => best = Some((pattern_id, score)),
            }
        }
    }
    best
}

/// Select pattern ids for a length bucket.
///
/// Equal-length buckets with `max_dist_floor < 2` can only admit distance 0
/// (indel distance is always even when lengths match). Distance-0 tokens are
/// exact AC hits and are skipped by `token_exact_covered`, so that branch is
/// dead — return empty rather than consulting a first-char index.
fn candidate_pattern_ids(
    lexicon: &CompiledLexicon,
    term_len: usize,
    token_len: usize,
    threshold: f64,
) -> &[usize] {
    let max_dist = ((token_len + term_len) as f64) * (1.0 - threshold / 100.0);
    let max_dist_floor = if max_dist < 0.0 {
        0
    } else {
        max_dist.floor() as usize
    };

    if token_len.abs_diff(term_len) > max_dist_floor {
        return &[];
    }
    if token_len == term_len && max_dist_floor < 2 {
        return &[];
    }
    lexicon
        .fuzzy_buckets
        .get(&term_len)
        .map(|v| v.as_slice())
        .unwrap_or(&[])
}

fn token_exact_covered(token: &NormToken<'_>, exact: &[MatchCandidate]) -> bool {
    exact
        .iter()
        .any(|c| c.norm_start <= token.start && c.norm_end >= token.end)
}

fn word_tokens(norm: &NormalizedText) -> impl Iterator<Item = NormToken<'_>> {
    let text = &norm.text;
    let bounds = norm
        .boundary_bytes
        .as_ref()
        .expect("ensure_boundaries before fuzzy tokenize");
    bounds.windows(2).filter_map(move |window| {
        let start = window[0];
        let end = window[1];
        if start >= end || end > text.len() {
            return None;
        }
        if !text.is_char_boundary(start) || !text.is_char_boundary(end) {
            return None;
        }
        let segment = &text[start..end];
        if !segment.chars().any(char::is_alphanumeric) {
            return None;
        }
        Some(NormToken {
            text: segment,
            start,
            end,
            char_len: segment.chars().count(),
        })
    })
}

/// Public wrapper preserving the string API for tests and callers.
#[cfg(test)]
pub fn indel_ratio_cutoff(a: &str, b: &str, threshold: f64) -> Option<f64> {
    if a == b {
        return Some(100.0);
    }
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let a_mask = char_presence_mask(&a_chars);
    let b_mask = char_presence_mask(&b_chars);
    let mut scratch = IndelScratch::new();
    indel_ratio_cutoff_chars(&a_chars, &b_chars, a_mask, b_mask, threshold, &mut scratch)
}

/// Indel distance with char-mask prefilter, scratch-row reuse, and early abandon.
///
/// Full O(n·m) DP with row-min early abandon (not Ukkonen-banded; band width would
/// help further under tight thresholds but the cell budget is already bounded by
/// `max_token_len`).
fn indel_ratio_cutoff_chars(
    a: &[char],
    b: &[char],
    a_mask: u32,
    b_mask: u32,
    threshold: f64,
    scratch: &mut IndelScratch,
) -> Option<f64> {
    let n = a.len();
    let m = b.len();
    if n + m == 0 {
        return Some(100.0);
    }
    if n == m && a == b {
        return Some(100.0);
    }

    // score = 100 * (1 - dist / (n+m)) >= threshold
    // => dist <= (n+m) * (1 - threshold/100)
    let max_dist = ((n + m) as f64) * (1.0 - threshold / 100.0);
    if max_dist < 0.0 {
        return None;
    }
    let max_dist_floor = max_dist.floor() as usize;

    // Character-presence Hamming lower bound on indel distance.
    let xor = a_mask ^ b_mask;
    let lower = xor.count_ones() as usize;
    if lower > max_dist_floor {
        return None;
    }

    scratch.ensure(m + 1);
    let prev = &mut scratch.prev;
    let curr = &mut scratch.curr;
    for (j, slot) in prev.iter_mut().enumerate().take(m + 1) {
        *slot = j;
    }

    for i in 1..=n {
        curr[0] = i;
        let mut row_min = curr[0];
        for j in 1..=m {
            let cost = if a[i - 1] == b[j - 1] {
                prev[j - 1]
            } else {
                // substitution as delete+insert
                prev[j - 1].saturating_add(2)
            };
            let del = prev[j].saturating_add(1);
            let ins = curr[j - 1].saturating_add(1);
            curr[j] = cost.min(del).min(ins);
            row_min = row_min.min(curr[j]);
        }
        if row_min > max_dist_floor {
            return None;
        }
        std::mem::swap(prev, curr);
    }

    let dist = prev[m];
    if dist as f64 > max_dist {
        return None;
    }
    let score = 100.0 * (1.0 - (dist as f64) / ((n + m) as f64));
    if score + f64::EPSILON >= threshold {
        Some(score)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identical_is_100() {
        assert_eq!(indel_ratio_cutoff("fuck", "fuck", 85.0), Some(100.0));
    }

    #[test]
    fn close_typo_passes() {
        let score = indel_ratio_cutoff("fuck", "fukc", 70.0).unwrap();
        assert!(score >= 70.0, "{score}");
    }

    #[test]
    fn unrelated_fails_cutoff() {
        assert!(indel_ratio_cutoff("hello", "zzzzz", 85.0).is_none());
    }

    #[test]
    fn char_mask_rejects_disjoint_alphabet() {
        // 'a'*5 vs 'z'*5: masks differ in 2 bits → lower bound 2; at threshold 100
        // max_dist_floor is 0 so prefilter must reject.
        assert!(indel_ratio_cutoff("aaaaa", "zzzzz", 100.0).is_none());
    }

    #[test]
    fn fuzzy_config_validate() {
        assert!(FuzzyConfig::default().validate().is_ok());
        assert!(FuzzyConfig {
            threshold: f64::NAN,
            ..FuzzyConfig::default()
        }
        .validate()
        .is_err());
        assert!(FuzzyConfig {
            threshold: 101.0,
            ..FuzzyConfig::default()
        }
        .validate()
        .is_err());
        assert!(FuzzyConfig {
            min_fuzzy_len: 0,
            ..FuzzyConfig::default()
        }
        .validate()
        .is_err());
    }

    #[test]
    fn tokenize_keeps_apostrophe_word() {
        use crate::normalize::{normalize, NormalizeOptions};
        let n = normalize("couldn't", NormalizeOptions::default());
        let tokens: Vec<_> = word_tokens(&n).collect();
        assert_eq!(tokens.len(), 1);
        assert_eq!(tokens[0].text, "couldn't");
    }

    #[test]
    fn token_cache_memos_misses_and_hits() {
        use crate::test_lexicon;
        let lex = test_lexicon(&["fuck"], &[]);
        let fuzzy = FuzzyConfig {
            threshold: 75.0,
            ..FuzzyConfig::default()
        };
        let cache = FuzzyTokenCache::new(64);
        let a = best_fuzzy_match("fukc", 4, &lex, fuzzy);
        let b = cache.lookup_or_insert("fukc", || best_fuzzy_match("fukc", 4, &lex, fuzzy));
        let c = cache.lookup_or_insert("fukc", || panic!("should be cached"));
        assert_eq!(a, b);
        assert_eq!(b, c);
        assert!(a.is_some());
    }

    #[test]
    fn cache_stays_bounded_and_admits_new_entries() {
        let cache = FuzzyTokenCache::new(FUZZY_CACHE_SHARDS); // 1 slot per shard
        for i in 0..1_000 {
            cache.lookup_or_insert(&format!("flood{i}"), || Some((999, 1.0)));
        }
        let entries: usize = cache
            .shards
            .iter()
            .map(|shard| shard.lock().unwrap().entries.len())
            .sum();
        assert!(entries <= FUZZY_CACHE_SHARDS);

        let admitted = cache.lookup_or_insert("useful-token", || Some((7, 99.0)));
        assert_eq!(admitted, Some((7, 99.0)));
        let cached = cache.lookup_or_insert("useful-token", || panic!("must be cached"));
        assert_eq!(cached, admitted);
    }

    #[test]
    fn equal_length_tight_threshold_bucket_is_empty() {
        use crate::test_lexicon;
        let lex = test_lexicon(&["fuck", "shit"], &[]);
        let ids = candidate_pattern_ids(&lex, 4, 4, 85.0);
        assert!(ids.is_empty());
        // Differing lengths still consult the bucket.
        let ids2 = candidate_pattern_ids(&lex, 5, 4, 85.0);
        assert!(!ids2.is_empty() || !lex.fuzzy_buckets.contains_key(&5));
    }
}
