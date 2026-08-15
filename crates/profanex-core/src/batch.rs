//! Order-preserving batch scanning with optional Rayon parallelism.

use std::sync::{Arc, Mutex, OnceLock};

use rayon::prelude::*;
use rayon::ThreadPool;

use crate::fuzzy::FuzzyTokenCache;
use crate::lexicon::CompiledLexicon;
use crate::mask::MaskStyle;
use crate::scan::{self, ScanConfig, ScanMatch};

#[derive(Debug, Clone, Copy, Default)]
pub struct BatchOptions {
    pub parallel: bool,
    /// When `parallel` is true, `None` uses Rayon's global pool; `Some(n)` uses a
    /// process-wide cached pool with `n` threads (`n >= 1`).
    pub workers: Option<usize>,
}

#[derive(Debug, thiserror::Error)]
pub enum BatchError {
    #[error("workers must be >= 1 when provided")]
    InvalidWorkers,
    #[error("workers requires parallel=True")]
    WorkersWithoutParallel,
    #[error("workers must be <= 256")]
    TooManyWorkers,
    #[error("failed to build rayon pool: {0}")]
    Pool(String),
}

pub fn validate_batch_options(opts: BatchOptions) -> Result<(), BatchError> {
    if let Some(n) = opts.workers {
        if n < 1 {
            return Err(BatchError::InvalidWorkers);
        }
        if n > 256 {
            return Err(BatchError::TooManyWorkers);
        }
        if !opts.parallel {
            return Err(BatchError::WorkersWithoutParallel);
        }
    }
    Ok(())
}

fn build_pool(n: usize) -> Result<ThreadPool, BatchError> {
    rayon::ThreadPoolBuilder::new()
        .num_threads(n)
        .build()
        .map_err(|e| BatchError::Pool(e.to_string()))
}

type CachedPool = Mutex<Option<(usize, Arc<ThreadPool>)>>;

fn cached_pool(n: usize) -> Result<Arc<ThreadPool>, BatchError> {
    // Retain only the most recently requested custom pool. This preserves the
    // common repeated-batch fast path without leaking one permanent thread pool
    // for every distinct user-provided worker count.
    static POOL: OnceLock<CachedPool> = OnceLock::new();
    let slot = POOL.get_or_init(|| Mutex::new(None));
    let mut guard = slot.lock().map_err(|e| BatchError::Pool(e.to_string()))?;
    if let Some((workers, pool)) = guard.as_ref() {
        if *workers == n {
            return Ok(Arc::clone(pool));
        }
    }
    let pool = Arc::new(build_pool(n)?);
    *guard = Some((n, Arc::clone(&pool)));
    Ok(pool)
}

fn map_texts<S, T, F>(texts: &[S], opts: BatchOptions, f: F) -> Result<Vec<T>, BatchError>
where
    S: AsRef<str> + Sync,
    T: Send,
    F: Fn(&str) -> T + Sync,
{
    validate_batch_options(opts)?;
    if !opts.parallel || texts.len() <= 1 {
        return Ok(texts.iter().map(|t| f(t.as_ref())).collect());
    }

    let run = || texts.par_iter().map(|t| f(t.as_ref())).collect();

    match opts.workers {
        None => Ok(run()),
        Some(n) => {
            let pool = cached_pool(n)?;
            Ok(pool.install(run))
        }
    }
}

pub fn contains_many<S: AsRef<str> + Sync>(
    texts: &[S],
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    opts: BatchOptions,
    cache: Option<&FuzzyTokenCache>,
) -> Result<Vec<bool>, BatchError> {
    map_texts(texts, opts, |t| scan::contains(t, lexicon, config, cache))
}

pub fn find_many<S: AsRef<str> + Sync>(
    texts: &[S],
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    opts: BatchOptions,
    cache: Option<&FuzzyTokenCache>,
) -> Result<Vec<Vec<ScanMatch>>, BatchError> {
    map_texts(texts, opts, |t| {
        scan::find_matches(t, lexicon, config, cache)
    })
}

pub fn clean_many<S: AsRef<str> + Sync>(
    texts: &[S],
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    style: MaskStyle,
    opts: BatchOptions,
    cache: Option<&FuzzyTokenCache>,
) -> Result<Vec<String>, BatchError> {
    map_texts(texts, opts, |t| {
        scan::clean(t, lexicon, config, style, cache)
    })
}

pub fn analyze_many<S: AsRef<str> + Sync>(
    texts: &[S],
    lexicon: &CompiledLexicon,
    config: ScanConfig,
    style: MaskStyle,
    opts: BatchOptions,
    cache: Option<&FuzzyTokenCache>,
) -> Result<Vec<(bool, String)>, BatchError> {
    map_texts(texts, opts, |t| {
        scan::analyze(t, lexicon, config, style, cache)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_lexicon;
    use crate::ScanConfig;

    fn eng(words: &[&str]) -> CompiledLexicon {
        test_lexicon(words, &[])
    }

    #[test]
    fn serial_and_parallel_equal() {
        let lex = eng(&["fuck", "shit"]);
        let texts: Vec<String> = (0..64)
            .map(|i| {
                if i % 3 == 0 {
                    format!("row {i} fuck")
                } else if i % 3 == 1 {
                    format!("clean {i}")
                } else {
                    format!("shit #{i}")
                }
            })
            .collect();
        let cfg = ScanConfig::default();
        let serial = contains_many(
            &texts,
            &lex,
            cfg,
            BatchOptions {
                parallel: false,
                workers: None,
            },
            None,
        )
        .unwrap();
        let parallel = contains_many(
            &texts,
            &lex,
            cfg,
            BatchOptions {
                parallel: true,
                workers: Some(2),
            },
            None,
        )
        .unwrap();
        assert_eq!(serial, parallel);

        let s_clean = clean_many(
            &texts,
            &lex,
            cfg,
            MaskStyle::Stars,
            BatchOptions {
                parallel: false,
                workers: None,
            },
            None,
        )
        .unwrap();
        let p_clean = clean_many(
            &texts,
            &lex,
            cfg,
            MaskStyle::Stars,
            BatchOptions {
                parallel: true,
                workers: Some(2),
            },
            None,
        )
        .unwrap();
        assert_eq!(s_clean, p_clean);

        let s_find = find_many(
            &texts,
            &lex,
            cfg,
            BatchOptions {
                parallel: false,
                workers: None,
            },
            None,
        )
        .unwrap();
        let p_find = find_many(
            &texts,
            &lex,
            cfg,
            BatchOptions {
                parallel: true,
                workers: None,
            },
            None,
        )
        .unwrap();
        assert_eq!(s_find.len(), p_find.len());
        for (a, b) in s_find.iter().zip(p_find.iter()) {
            assert_eq!(a.len(), b.len());
            for (ma, mb) in a.iter().zip(b.iter()) {
                assert_eq!(ma.start, mb.start);
                assert_eq!(ma.end, mb.end);
                assert_eq!(ma.term, mb.term);
            }
        }
    }

    #[test]
    fn rejects_bad_workers() {
        assert!(validate_batch_options(BatchOptions {
            parallel: true,
            workers: Some(0)
        })
        .is_err());
        assert!(matches!(
            validate_batch_options(BatchOptions {
                parallel: true,
                workers: Some(257)
            }),
            Err(BatchError::TooManyWorkers)
        ));
        assert!(validate_batch_options(BatchOptions {
            parallel: false,
            workers: Some(2)
        })
        .is_err());
    }

    #[test]
    fn cached_pool_reuses_same_size() {
        let a = cached_pool(2).unwrap();
        let b = cached_pool(2).unwrap();
        assert!(Arc::ptr_eq(&a, &b));
    }
}
