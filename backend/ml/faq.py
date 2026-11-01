"""Deterministic local FAQ matcher over an approved fictional policy corpus.

Week 3 scope: keyword retrieval with explicit abstention. No network calls.
Week 4 will upgrade this to retrieval-augmented generation (RAG).

Task prompt (the contract this matcher follows, also used if an LLM path is
added later): "Answer ONLY from the approved FAQ entries provided. If the
entries do not clearly answer the question, or the question asks for medical,
diagnostic, triage, or treatment advice, reply that you cannot answer and
suggest contacting a qualified professional or support. Never invent facts."
"""
import json
import re
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "faq_corpus.json"
MIN_SCORE = 2
# Clinical / out-of-scope intents always abstain, even if keywords overlap.
BLOCKED = re.compile(
    r"\b(diagnos\w*|symptom\w*|treat\w*|medicat\w*|dose|dosage|prescri\w*|disease|"
    r"cancer|diabet\w*|pain|sick|illness|triage|emergency room|suicid\w*|pregnan\w*|cure)\b",
    re.I)
TOKEN = re.compile(r"[a-z0-9\-]+")
STOP = {"the", "a", "an", "is", "are", "my", "i", "do", "does", "can", "how", "what",
        "to", "of", "for", "in", "on", "me", "you", "it", "be", "and", "or", "with"}


@lru_cache
def corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text())


def _tokens(text: str) -> set[str]:
    return {t for t in TOKEN.findall(text.lower()) if t not in STOP}


def _score(question: str, entry: dict) -> int:
    q = question.lower()
    toks = _tokens(question)
    score = 0
    for kw in entry["keywords"]:
        if " " in kw:
            score += 2 if kw in q else 0
        elif kw in toks or (kw.rstrip("s") in toks) or (kw + "s") in toks:
            score += 1
    score += len(toks & _tokens(entry["title"]))
    return score


def answer(question: str) -> dict:
    if BLOCKED.search(question):
        return {"abstained": True, "reason": "out_of_scope_clinical",
                "answer": "I can't help with medical, diagnostic, or treatment questions. "
                          "Please contact a qualified healthcare professional.",
                "sources": []}
    ranked = sorted(((_score(question, e), e) for e in corpus()["entries"]),
                    key=lambda p: p[0], reverse=True)
    best_score, best = ranked[0]
    if best_score < MIN_SCORE:
        return {"abstained": True, "reason": "unsupported",
                "answer": "I don't have an approved answer for that. Please contact support.",
                "sources": []}
    return {"abstained": False, "reason": None, "answer": best["answer"],
            "sources": [{"id": best["id"], "title": best["title"], "score": best_score}]}
