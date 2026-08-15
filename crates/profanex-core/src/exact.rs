//! Exact and phrase candidate collection.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MatchKind {
    Exact,
    Phrase,
    Fuzzy,
}

impl MatchKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Exact => "exact",
            Self::Phrase => "phrase",
            Self::Fuzzy => "fuzzy",
        }
    }

    pub fn priority(self) -> u8 {
        match self {
            Self::Exact | Self::Phrase => 0,
            Self::Fuzzy => 1,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn as_str_and_priority() {
        assert_eq!(MatchKind::Exact.as_str(), "exact");
        assert_eq!(MatchKind::Phrase.as_str(), "phrase");
        assert_eq!(MatchKind::Fuzzy.as_str(), "fuzzy");
        assert_eq!(MatchKind::Exact.priority(), 0);
        assert_eq!(MatchKind::Phrase.priority(), 0);
        assert_eq!(MatchKind::Fuzzy.priority(), 1);
    }
}
