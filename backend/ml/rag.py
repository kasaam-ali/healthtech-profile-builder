"""Week 4 local RAG over approved fictional clinic policy documents.

Offline by design: TF-IDF retrieval (scikit-learn), extractive answers, citations.
No network, no API keys. Answers are built only from retrieved chunks; when evidence
is weak, the question is medical, or it looks like a prompt injection, we abstain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DOCS_DIR = Path(__file__).resolve().parent / "clinic_docs"

MEDICAL = re.compile(
    r"\b(diagnos\w*|symptom\w*|medicat\w*|medicine|dose|dosage|treat\w*|prescri\w*|pain|"
    r"chest|fever|headache|ache|disease|cancer|diabet\w*|pill\w*|drug\w*|triage|blood pressure)\b", re.I)
INJECTION = re.compile(
    r"(ignore (all |the |any )?(previous|prior|above)|disregard .*instructions|system prompt|"
    r"you are now|developer mode|reveal .*(prompt|secret|key|token)|jailbreak|act as)", re.I)


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


def _parse(path: Path) -> tuple[str, str, str]:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\nid:\s*(.+?)\s*\ntitle:\s*(.+?)\s*\n---\s*\n(.*)$", raw, re.S)
    if not m:
        raise RetrievalError(f"Document {path.name} is missing front matter")
    return m.group(1), m.group(2), m.group(3)


@lru_cache
def load_chunks(docs_dir: str = str(DOCS_DIR)) -> tuple[Chunk, ...]:
    """Chunk = one paragraph. Small policy docs make paragraphs a natural unit."""
    files = sorted(Path(docs_dir).glob("*.md"))
    if not files:
        raise RetrievalError("No approved documents found")
    out = []
    for f in files:
        doc_id, title, body = _parse(f)
        for i, para in enumerate(p.strip() for p in body.split("\n\n") if p.strip()):
            out.append(Chunk(f"{doc_id}#{i + 1}", doc_id, title, " ".join(para.split())))
    return tuple(out)


@lru_cache
def _index(setting_name: str, docs_dir: str = str(DOCS_DIR)):
    s = SETTINGS[setting_name]
    chunks = load_chunks(docs_dir)
    vec = TfidfVectorizer(ngram_range=s.ngram_range, sublinear_tf=s.sublinear_tf,
                          stop_words="english")
    matrix = vec.fit_transform([f"{c.title}. {c.text}" for c in chunks])
    return vec, matrix, chunks


def retrieve(query: str, setting_name: str = DEFAULT_SETTING, *, simulate_failure: bool = False,
             docs_dir: str = str(DOCS_DIR)) -> list[dict]:
    if setting_name not in SETTINGS:
        raise ValueError(f"Unknown setting {setting_name}")
    if simulate_failure:
        raise RetrievalError("Retrieval provider timed out (simulated)")
    s = SETTINGS[setting_name]
    vec, matrix, chunks = _index(setting_name, docs_dir)
    scores = cosine_similarity(vec.transform([query]), matrix)[0]
    ranked = sorted(range(len(chunks)), key=lambda i: -scores[i])[: s.top_k]
    return [{"chunk_id": chunks[i].chunk_id, "doc_id": chunks[i].doc_id,
             "title": chunks[i].title, "text": chunks[i].text,
             "score": round(float(scores[i]), 4)} for i in ranked if scores[i] > 0]


def answer(question: str, setting_name: str = DEFAULT_SETTING, *,
           simulate_failure: bool = False) -> dict:
    """Returns {abstained, reason, answer, citations, setting}. Raises RetrievalError."""
    base = {"setting": setting_name, "citations": []}
    if INJECTION.search(question):
        return {**base, "abstained": True, "reason": "prompt_injection",
                "answer": "I can only answer questions about clinic policy from approved documents."}
    if MEDICAL.search(question):
        return {**base, "abstained": True, "reason": "medical",
                "answer": ("I cannot help with medical questions. Please speak with a licensed "
                           "clinician, or contact local emergency services if urgent.")}
    hits = retrieve(question, setting_name, simulate_failure=simulate_failure)
    s = SETTINGS[setting_name]
    good = [h for h in hits if h["score"] >= s.min_score]
    if not good:
        return {**base, "abstained": True, "reason": "insufficient_evidence",
                "answer": "I could not find this in the approved clinic documents.",
                "top_score": hits[0]["score"] if hits else 0.0}
    best = good[0]
    support = [h for h in good if h["score"] >= best["score"] * 0.6]
    return {**base, "abstained": False, "reason": None,
            "answer": " ".join(h["text"] for h in support),
            "citations": [{"doc_id": h["doc_id"], "title": h["title"], "chunk_id": h["chunk_id"],
                           "score": h["score"]} for h in support],
            "top_score": best["score"]}
