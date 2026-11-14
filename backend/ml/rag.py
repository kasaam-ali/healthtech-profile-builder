"""Week 4 local RAG over approved fictional clinic policy documents.

Offline by design: TF-IDF retrieval (scikit-learn), extractive answers, citations.
No network, no API keys. Answers are built only from retrieved chunks; when evidence
is weak, the question is medical, or it looks like a prompt injection, we abstain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCS_DIR = Path(__file__).resolve().parent / "clinic_docs"

MEDICAL = re.compile(
    r"\b(diagnos\w*|symptom\w*|medicat\w*|medicine|dose|dosage|treat\w*|prescri\w*|pain|"
    r"chest|fever|headache|ache|disease|cancer|diabet\w*|pill\w*|drug\w*|triage|blood pressure)\b", re.I)
INJECTION = re.compile(
    r"(ignore (all |the |any )?(previous|prior|above)|disregard .*instructions|system prompt|"
    r"you are now|developer mode|reveal .*(prompt|secret|key|token)|jailbreak|act as)", re.I)

STOP_TERMS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "cant", "cannot", "could", "couldnt", "did", "didn", "do", "does",
    "doesn", "doing", "dont", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadnt", "has", "hasnt", "have", "havent", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isnt", "it", "its", "itself",
    "lets", "me", "more", "most", "mustnt", "my", "myself", "no", "nor", "not", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shant", "she", "should", "shouldnt", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasnt", "we", "were", "werent", "what",
    "when", "where", "which", "while", "who", "whom", "why", "with", "wont", "would", "wouldnt",
    "you", "your", "yours", "yourself", "yourselves",
    # Question framing, filler, and ubiquitous corpus-wide terms:
    "many", "much", "tell", "please", "like", "recommend", "work", "good", "one", "change",
    "clinic", "northwind", "wellness", "policy", "doe",
}


@dataclass(frozen=True)
class Setting:
    name: str
    ngram_range: tuple[int, int]
    sublinear_tf: bool
    top_k: int
    min_score: float


SETTINGS = {
    "baseline": Setting("baseline", (1, 1), False, 3, 0.10),
    "tuned": Setting("tuned", (1, 2), True, 2, 0.14),
}
DEFAULT_SETTING = "tuned"


class RetrievalError(RuntimeError):
    """Raised when the index or provider is unavailable. Callers return 503."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    text: str


def _stem(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        return w[:-1]
    return w


def _extract_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(w) for w in words if _stem(w) not in STOP_TERMS and len(w) >= 3}


def _parse(path: Path) -> tuple[str, str, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise RetrievalError(f"Cannot read document {path.name}: {type(exc).__name__}") from exc
    m = re.match(r"^---\s*\nid:\s*(.+?)\s*\ntitle:\s*(.+?)\s*\n---\s*\n(.*)$", raw, re.S)
    if not m:
        raise RetrievalError(f"Document {path.name} is missing front matter")
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()


_chunks_cache: dict[tuple, tuple[Chunk, ...]] = {}
_index_cache: dict[tuple, tuple[TfidfVectorizer, Any, tuple[Chunk, ...]]] = {}


def _get_docs_signature(docs_path: Path) -> tuple[tuple[str, int, int], ...]:
    if not docs_path.is_dir():
        raise RetrievalError(f"Documents directory not found: {docs_path.name}")
    files = sorted(docs_path.glob("*.md"))
    if not files:
        raise RetrievalError("No approved documents found")
    sig = []
    for f in files:
        try:
            st = f.stat()
            sig.append((f.name, st.st_mtime_ns, st.st_size))
        except OSError as exc:
            raise RetrievalError(f"Cannot inspect document {f.name}: {type(exc).__name__}") from exc
    return tuple(sig)


def load_chunks(docs_dir: str | Path | None = None) -> tuple[Chunk, ...]:
    """Chunk = one paragraph. Small policy docs make paragraphs a natural unit.
    Cached by directory file signatures (name, mtime, size) so updates reload cleanly."""
    path = Path(docs_dir if docs_dir is not None else DOCS_DIR)
    sig = _get_docs_signature(path)
    if sig in _chunks_cache:
        return _chunks_cache[sig]

    files = sorted(path.glob("*.md"))
    out = []
    for f in files:
        doc_id, title, body = _parse(f)
        for i, para in enumerate(p.strip() for p in body.split("\n\n") if p.strip()):
            out.append(Chunk(f"{doc_id}#{i + 1}", doc_id, title, " ".join(para.split())))
    result = tuple(out)
    _chunks_cache[sig] = result
    return result


def _index(setting_name: str, docs_dir: str | Path | None = None):
    s = SETTINGS[setting_name]
    path = Path(docs_dir if docs_dir is not None else DOCS_DIR)
    sig = _get_docs_signature(path)
    cache_key = (setting_name, sig)
    if cache_key in _index_cache:
        return _index_cache[cache_key]

    chunks = load_chunks(path)
    try:
        vec = TfidfVectorizer(ngram_range=s.ngram_range, sublinear_tf=s.sublinear_tf,
                              stop_words="english")
        matrix = vec.fit_transform([f"{c.title}. {c.text}" for c in chunks])
    except Exception as exc:
        raise RetrievalError(f"Index construction failed: {type(exc).__name__}") from exc
    result = (vec, matrix, chunks)
    _index_cache[cache_key] = result
    return result


def retrieve(query: str, setting_name: str = DEFAULT_SETTING, *, simulate_failure: bool = False,
             docs_dir: str | Path | None = None) -> list[dict]:
    if setting_name not in SETTINGS:
        raise ValueError(f"Unknown setting {setting_name}")
    if simulate_failure:
        raise RetrievalError("Retrieval provider timed out (simulated)")
    s = SETTINGS[setting_name]
    path = Path(docs_dir if docs_dir is not None else DOCS_DIR)
    vec, matrix, chunks = _index(setting_name, path)
    try:
        scores = cosine_similarity(vec.transform([query]), matrix)[0]
    except Exception as exc:
        raise RetrievalError(f"Similarity computation failed: {type(exc).__name__}") from exc
    ranked = sorted(range(len(chunks)), key=lambda i: -scores[i])[: s.top_k]
    return [{"chunk_id": chunks[i].chunk_id, "doc_id": chunks[i].doc_id,
             "title": chunks[i].title, "text": chunks[i].text,
             "score": round(float(scores[i]), 4)} for i in ranked if scores[i] > 0]


def answer(question: str, setting_name: str = DEFAULT_SETTING, *,
           simulate_failure: bool = False, docs_dir: str | Path | None = None) -> dict:
    """Returns {abstained, reason, answer, citations, setting}. Raises RetrievalError."""
    base = {"setting": setting_name, "citations": []}
    if INJECTION.search(question):
        return {**base, "abstained": True, "reason": "prompt_injection",
                "answer": "I can only answer questions about clinic policy from approved documents."}
    if MEDICAL.search(question):
        return {**base, "abstained": True, "reason": "medical",
                "answer": ("I cannot help with medical questions. Please speak with a licensed "
                           "clinician, or contact local emergency services if urgent.")}

    path = Path(docs_dir if docs_dir is not None else DOCS_DIR)
    # Pre-compute corpus vocabulary from approved chunks for grounded evidence verification
    chunks = load_chunks(path)
    corpus_terms: set[str] = set()
    for c in chunks:
        corpus_terms.update(_extract_terms(c.title + " " + c.text))

    q_terms = _extract_terms(question)
    # Ambiguous or content-free questions (e.g. "Can I change it?") must abstain
    if not q_terms:
        return {**base, "abstained": True, "reason": "insufficient_evidence",
                "answer": "I could not find this in the approved clinic documents.",
                "top_score": 0.0}

    # Check whether the question asks for topics/nouns completely unsupported by the corpus
    supported_q_terms = q_terms & corpus_terms
    unsupported_q_terms = q_terms - corpus_terms
    if not supported_q_terms or len(unsupported_q_terms) > len(supported_q_terms):
        return {**base, "abstained": True, "reason": "insufficient_evidence",
                "answer": "I could not find this in the approved clinic documents.",
                "top_score": 0.0}

    hits = retrieve(question, setting_name, simulate_failure=simulate_failure, docs_dir=docs_dir)
    s = SETTINGS[setting_name]
    good = [h for h in hits if h["score"] >= s.min_score]
    if not good:
        return {**base, "abstained": True, "reason": "insufficient_evidence",
                "answer": "I could not find this in the approved clinic documents.",
                "top_score": hits[0]["score"] if hits else 0.0}

    # The top retrieved chunk must have topical evidence overlap with the question
    best = good[0]
    best_terms = _extract_terms(best["title"] + " " + best["text"])
    if not (q_terms & best_terms):
        return {**base, "abstained": True, "reason": "insufficient_evidence",
                "answer": "I could not find this in the approved clinic documents.",
                "top_score": best["score"]}

    # Filter support chunks to those with high score AND verified topical overlap
    support = [h for h in good if h["score"] >= best["score"] * 0.6 and
               bool(q_terms & _extract_terms(h["title"] + " " + h["text"]))]
    if not support:
        support = [best]

    return {**base, "abstained": False, "reason": None,
            "answer": " ".join(h["text"] for h in support),
            "citations": [{"doc_id": h["doc_id"], "title": h["title"], "chunk_id": h["chunk_id"],
                           "score": h["score"]} for h in support],
            "top_score": best["score"]}
