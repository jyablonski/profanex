//! Deterministic non-overlapping candidate resolution.

use std::collections::BTreeMap;

use crate::exact::MatchKind;

/// A candidate match in original UTF-8 byte space (pre-Python index conversion).
///
/// `term` is looked up from lexicon metadata via `pattern_id` after resolution
/// to avoid cloning strings for discarded overlapping candidates.
#[derive(Debug, Clone)]
pub struct MatchCandidate {
    pub orig_start: usize,
    pub orig_end: usize,
    pub norm_start: usize,
    pub norm_end: usize,
    pub pattern_id: usize,
    pub categories: u32,
    pub score: f64,
    pub kind: MatchKind,
}

/// Resolve overlapping candidates into a deterministic non-overlapping set.
///
/// Priority: exact/phrase over fuzzy, earlier start, longer original span,
/// higher score, then lower pattern id (stable). Same span + pattern merges
/// category bits.
pub fn resolve_candidates(mut candidates: Vec<MatchCandidate>) -> Vec<MatchCandidate> {
    if candidates.is_empty() {
        return candidates;
    }

    // Merge identical span+pattern category metadata first.
    candidates.sort_by(|a, b| {
        a.orig_start
            .cmp(&b.orig_start)
            .then(a.orig_end.cmp(&b.orig_end))
            .then(a.pattern_id.cmp(&b.pattern_id))
    });

    let mut merged: Vec<MatchCandidate> = Vec::with_capacity(candidates.len());
    for c in candidates {
        if let Some(last) = merged.last_mut() {
            if last.orig_start == c.orig_start
                && last.orig_end == c.orig_end
                && last.pattern_id == c.pattern_id
            {
                last.categories |= c.categories;
                if c.score > last.score {
                    last.score = c.score;
                }
                continue;
            }
        }
        merged.push(c);
    }

    // Sort by acceptance priority. Pattern id breaks ties deterministically
    // (lexicon compile order is BTreeMap by normalized pattern).
    merged.sort_by(|a, b| {
        a.kind
            .priority()
            .cmp(&b.kind.priority())
            .then(a.orig_start.cmp(&b.orig_start))
            .then(b.orig_end.cmp(&a.orig_end)) // longer span first
            .then(
                b.score
                    .partial_cmp(&a.score)
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
            .then(a.pattern_id.cmp(&b.pattern_id))
    });

    // Greedy non-overlap with an ordered interval set: O(log n) overlap test
    // per candidate (accepted intervals are disjoint, so predecessor + successor
    // suffice). Keyed by orig_start.
    let mut accepted: BTreeMap<usize, MatchCandidate> = BTreeMap::new();
    for c in merged {
        if interval_overlaps_accepted(&accepted, c.orig_start, c.orig_end) {
            continue;
        }
        accepted.insert(c.orig_start, c);
    }

    accepted.into_values().collect()
}

/// True when `[start, end)` overlaps any disjoint interval in `accepted`.
fn interval_overlaps_accepted(
    accepted: &BTreeMap<usize, MatchCandidate>,
    start: usize,
    end: usize,
) -> bool {
    if let Some((_, pred)) = accepted.range(..start).next_back() {
        if pred.orig_end > start {
            return true;
        }
    }
    if let Some((_, succ)) = accepted.range(start..).next() {
        if succ.orig_start < end {
            return true;
        }
    }
    false
}

/// Allowlist intervals indexed for O(log n) containment queries.
#[derive(Debug, Default)]
pub(crate) struct CoverRanges {
    starts: Vec<usize>,
    prefix_max_ends: Vec<usize>,
}

impl CoverRanges {
    pub(crate) fn new(mut ranges: Vec<(usize, usize)>) -> Self {
        ranges.sort_unstable_by_key(|&(start, end)| (start, end));
        let mut starts = Vec::with_capacity(ranges.len());
        let mut prefix_max_ends = Vec::with_capacity(ranges.len());
        let mut max_end = 0usize;
        for (start, end) in ranges {
            starts.push(start);
            max_end = max_end.max(end);
            prefix_max_ends.push(max_end);
        }
        Self {
            starts,
            prefix_max_ends,
        }
    }

    /// True when an indexed interval fully covers `[start, end)`.
    pub(crate) fn covers(&self, start: usize, end: usize) -> bool {
        let eligible = self
            .starts
            .partition_point(|&allow_start| allow_start <= start);
        eligible > 0 && self.prefix_max_ends[eligible - 1] >= end
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cand(start: usize, end: usize, pattern_id: usize, kind: MatchKind) -> MatchCandidate {
        MatchCandidate {
            orig_start: start,
            orig_end: end,
            norm_start: start,
            norm_end: end,
            pattern_id,
            categories: 1,
            score: 100.0,
            kind,
        }
    }

    #[test]
    fn prefers_longer_span() {
        let got = resolve_candidates(vec![
            cand(0, 3, 0, MatchKind::Exact),
            cand(0, 7, 1, MatchKind::Exact),
        ]);
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].pattern_id, 1);
        assert_eq!(got[0].orig_end, 7);
    }

    #[test]
    fn merges_same_span_pattern_categories() {
        let mut a = cand(0, 4, 0, MatchKind::Exact);
        a.categories = 1;
        a.score = 90.0;
        let mut b = cand(0, 4, 0, MatchKind::Exact);
        b.categories = 2;
        b.score = 95.0;
        let got = resolve_candidates(vec![a, b]);
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].categories, 3);
        assert_eq!(got[0].score, 95.0);
    }

    #[test]
    fn empty_input() {
        assert!(resolve_candidates(vec![]).is_empty());
    }

    #[test]
    fn dense_non_overlapping_preserves_all() {
        let cands: Vec<_> = (0..100)
            .map(|i| cand(i * 5, i * 5 + 4, i, MatchKind::Exact))
            .collect();
        let got = resolve_candidates(cands);
        assert_eq!(got.len(), 100);
        for (i, c) in got.iter().enumerate() {
            assert_eq!(c.orig_start, i * 5);
        }
    }

    #[test]
    fn dense_overlapping_keeps_earlier_priority() {
        // All start at 0 with increasing length — longest wins once.
        let cands: Vec<_> = (1..=50).map(|i| cand(0, i, i, MatchKind::Exact)).collect();
        let got = resolve_candidates(cands);
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].orig_end, 50);
    }

    #[test]
    fn overlap_helper_half_open() {
        let overlap = |a0: usize, a1: usize, b0: usize, b1: usize| a0 < b1 && b0 < a1;
        assert!(overlap(0, 5, 4, 8));
        assert!(!overlap(0, 5, 5, 8));
        assert!(overlap(0, 10, 3, 4));
    }

    #[test]
    fn cover_ranges_handles_unsorted_nested_intervals() {
        let ranges = CoverRanges::new(vec![(20, 30), (0, 4), (2, 12), (40, 41)]);
        assert!(ranges.covers(3, 10));
        assert!(ranges.covers(20, 30));
        assert!(!ranges.covers(3, 13));
        assert!(!ranges.covers(12, 20));
        assert!(!CoverRanges::default().covers(0, 1));
    }
}
