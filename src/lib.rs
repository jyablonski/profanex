//! Private PyO3 extension module `profanex._core`.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedStr;
use pyo3::types::{PyDict, PyList, PyTuple};

use profanex_core::{
    scan, BatchOptions, CompiledLexicon, FuzzyConfig, FuzzyTokenCache, LexiconTerm, MaskStyle,
    NormalizeOptions, ScanConfig, ScanMatch,
};

/// Maps original UTF-8 byte offsets to Python code-point indices.
enum PyIndex {
    /// ASCII: byte offset == code-point index.
    Ascii,
    /// Non-ASCII: `starts[i]` is the byte offset of Python index `i`; final entry is `len`.
    Sparse(Vec<usize>),
}

impl PyIndex {
    fn new(text: &str) -> Self {
        if text.is_ascii() {
            return Self::Ascii;
        }
        let mut starts: Vec<usize> = text.char_indices().map(|(i, _)| i).collect();
        starts.push(text.len());
        Self::Sparse(starts)
    }

    fn index(&self, byte_offset: usize) -> Option<usize> {
        match self {
            Self::Ascii => Some(byte_offset),
            Self::Sparse(starts) => starts.binary_search(&byte_offset).ok(),
        }
    }
}

fn parse_mask(style: &str) -> PyResult<MaskStyle> {
    match style {
        "stars" => Ok(MaskStyle::Stars),
        "vowels" => Ok(MaskStyle::Vowels),
        other => Err(PyValueError::new_err(format!(
            "unsupported mask style: {other}"
        ))),
    }
}

fn dict_get<'py, T: pyo3::FromPyObject<'py>>(d: &Bound<'py, PyDict>, key: &str) -> PyResult<T> {
    d.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("banned entry missing '{key}'")))?
        .extract()
}

fn batch_opts(parallel: bool, workers: Option<usize>) -> PyResult<BatchOptions> {
    let opts = BatchOptions { parallel, workers };
    profanex_core::validate_batch_options(opts)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(opts)
}

fn match_to_tuple<'py>(
    py: Python<'py>,
    text: &str,
    m: &ScanMatch,
    py_index: &PyIndex,
) -> PyResult<Bound<'py, PyTuple>> {
    if m.start > text.len()
        || m.end > text.len()
        || !text.is_char_boundary(m.start)
        || !text.is_char_boundary(m.end)
    {
        return Err(PyRuntimeError::new_err("invalid match byte span"));
    }
    let start = py_index
        .index(m.start)
        .ok_or_else(|| PyRuntimeError::new_err("invalid match byte span"))?;
    let end = py_index
        .index(m.end)
        .ok_or_else(|| PyRuntimeError::new_err("invalid match byte span"))?;
    (
        start,
        end,
        &text[m.start..m.end],
        m.term.as_str(),
        m.categories,
        m.score,
        m.kind.as_str(),
    )
        .into_pyobject(py)
}

#[pyclass(module = "profanex._core", name = "Engine")]
struct Engine {
    lexicon: CompiledLexicon,
    scan: ScanConfig,
    mask: MaskStyle,
    fuzzy_cache: FuzzyTokenCache,
}

#[pymethods]
impl Engine {
    /// Create a compiled engine.
    ///
    /// `banned` is a list of dicts: `{term, pattern, categories}` where categories is an int bitfield.
    /// `allowlist` is a list of pattern strings.
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        banned,
        allowlist,
        *,
        word_boundaries=true,
        normalize_leet=true,
        normalize_repeated_chars=false,
        normalize_separated_runs=false,
        enable_fuzzy=false,
        threshold=85.0,
        min_fuzzy_len=4,
        fuzzy_length_delta=2,
        fuzzy_max_token_len=64,
        mask="stars"
    ))]
    fn new(
        banned: &Bound<'_, PyList>,
        allowlist: Vec<String>,
        word_boundaries: bool,
        normalize_leet: bool,
        normalize_repeated_chars: bool,
        normalize_separated_runs: bool,
        enable_fuzzy: bool,
        threshold: f64,
        min_fuzzy_len: usize,
        fuzzy_length_delta: usize,
        fuzzy_max_token_len: usize,
        mask: &str,
    ) -> PyResult<Self> {
        if !(0.0..=100.0).contains(&threshold) {
            return Err(PyValueError::new_err("threshold must be in 0..=100"));
        }
        if min_fuzzy_len < 1 {
            return Err(PyValueError::new_err("min_fuzzy_len must be >= 1"));
        }
        if fuzzy_max_token_len < min_fuzzy_len {
            return Err(PyValueError::new_err(
                "fuzzy_max_token_len must be >= min_fuzzy_len",
            ));
        }

        let fuzzy = FuzzyConfig {
            threshold,
            min_fuzzy_len,
            length_delta: fuzzy_length_delta,
            max_token_len: fuzzy_max_token_len,
        };
        fuzzy.validate().map_err(PyValueError::new_err)?;

        let mut terms = Vec::with_capacity(banned.len());
        for item in banned.iter() {
            let d = item.downcast::<PyDict>()?;
            terms.push(LexiconTerm {
                term: dict_get(d, "term")?,
                pattern: dict_get(d, "pattern")?,
                categories: dict_get(d, "categories")?,
            });
        }

        let opts = NormalizeOptions {
            normalize_leet,
            canonical_separators: true,
            normalize_repeated_chars,
            normalize_separated_runs,
        };
        let lexicon = CompiledLexicon::compile(&terms, &allowlist, opts)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        Ok(Self {
            lexicon,
            scan: ScanConfig {
                word_boundaries,
                enable_fuzzy,
                fuzzy,
            },
            mask: parse_mask(mask)?,
            fuzzy_cache: FuzzyTokenCache::default(),
        })
    }

    fn contains(&self, py: Python<'_>, text: PyBackedStr) -> bool {
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let cache = Some(&self.fuzzy_cache);
        py.allow_threads(|| scan::contains(text.as_ref(), lexicon, scan, cache))
    }

    fn find<'py>(&self, py: Python<'py>, text: PyBackedStr) -> PyResult<Bound<'py, PyList>> {
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let cache = Some(&self.fuzzy_cache);
        let matches = py.allow_threads(|| scan::find_matches(text.as_ref(), lexicon, scan, cache));
        if matches.is_empty() {
            return Ok(PyList::empty(py));
        }
        let py_index = PyIndex::new(text.as_ref());
        let list = PyList::empty(py);
        for m in &matches {
            list.append(match_to_tuple(py, text.as_ref(), m, &py_index)?)?;
        }
        Ok(list)
    }

    fn clean(&self, py: Python<'_>, text: PyBackedStr) -> String {
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let mask = self.mask;
        let cache = Some(&self.fuzzy_cache);
        py.allow_threads(|| scan::clean(text.as_ref(), lexicon, scan, mask, cache))
    }

    fn analyze(&self, py: Python<'_>, text: PyBackedStr) -> (bool, String) {
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let mask = self.mask;
        let cache = Some(&self.fuzzy_cache);
        py.allow_threads(|| scan::analyze(text.as_ref(), lexicon, scan, mask, cache))
    }

    #[pyo3(signature = (texts, *, parallel=false, workers=None))]
    fn contains_many(
        &self,
        py: Python<'_>,
        texts: Vec<PyBackedStr>,
        parallel: bool,
        workers: Option<usize>,
    ) -> PyResult<Vec<bool>> {
        let opts = batch_opts(parallel, workers)?;
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let cache = Some(&self.fuzzy_cache);
        py.allow_threads(|| profanex_core::contains_many(&texts, lexicon, scan, opts, cache))
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    #[pyo3(signature = (texts, *, parallel=false, workers=None))]
    fn find_many<'py>(
        &self,
        py: Python<'py>,
        texts: Vec<PyBackedStr>,
        parallel: bool,
        workers: Option<usize>,
    ) -> PyResult<Bound<'py, PyList>> {
        let opts = batch_opts(parallel, workers)?;
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let cache = Some(&self.fuzzy_cache);
        let nested = py
            .allow_threads(|| profanex_core::find_many(&texts, lexicon, scan, opts, cache))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let outer = PyList::empty(py);
        for (text, matches) in texts.iter().zip(nested.iter()) {
            if matches.is_empty() {
                outer.append(PyList::empty(py))?;
                continue;
            }
            let py_index = PyIndex::new(text.as_ref());
            let inner = PyList::empty(py);
            for m in matches {
                inner.append(match_to_tuple(py, text.as_ref(), m, &py_index)?)?;
            }
            outer.append(inner)?;
        }
        Ok(outer)
    }

    #[pyo3(signature = (texts, *, parallel=false, workers=None))]
    fn clean_many(
        &self,
        py: Python<'_>,
        texts: Vec<PyBackedStr>,
        parallel: bool,
        workers: Option<usize>,
    ) -> PyResult<Vec<String>> {
        let opts = batch_opts(parallel, workers)?;
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let mask = self.mask;
        let cache = Some(&self.fuzzy_cache);
        py.allow_threads(|| profanex_core::clean_many(&texts, lexicon, scan, mask, opts, cache))
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    #[pyo3(signature = (texts, *, parallel=false, workers=None))]
    fn analyze_many(
        &self,
        py: Python<'_>,
        texts: Vec<PyBackedStr>,
        parallel: bool,
        workers: Option<usize>,
    ) -> PyResult<(Vec<bool>, Vec<String>)> {
        let opts = batch_opts(parallel, workers)?;
        let lexicon = &self.lexicon;
        let scan = self.scan;
        let mask = self.mask;
        let cache = Some(&self.fuzzy_cache);
        let analyzed = py
            .allow_threads(|| profanex_core::analyze_many(&texts, lexicon, scan, mask, opts, cache))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(analyzed.into_iter().unzip())
    }
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Engine>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
