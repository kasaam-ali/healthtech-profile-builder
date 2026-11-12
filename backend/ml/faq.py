"""Deterministic local FAQ matcher over an approved fictional policy corpus.

Week 3 scope: evidence-group retrieval with explicit abstention. No network calls.
Week 4 will upgrade this to retrieval-augmented generation (RAG).

Task prompt (the contract this matcher follows, also used if an LLM path is
added later): "Answer ONLY from the approved FAQ entries provided. If the
entries do not clearly answer the question, or the question asks for medical,
diagnostic, triage, or treatment advice, reply that you cannot answer and
suggest contacting a qualified professional or support. Never invent facts."

Matching rules (review fix for PR #4):
1. Clinical intent always abstains first.
2. An entry is supported only if the question hits at least one term from
   EVERY evidence group of that entry. The first group is the topic group, so
   a generic phrase such as "how many" can never answer on its own.
3. If more than one entry has topic evidence, the intent is ambiguous or
   mixed, so we abstain instead of guessing.
4. If the question has a second clause ("... and how many doctors ...") without
   topic evidence for the chosen entry, it is mixed intent and we abstain.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "faq_corpus.json"
# Clinical / out-of-scope intents always abstain, even if keywords overlap.
BLOCKED = re.compile(
    r"\b(diagnos\w*|symptom\w*|treat\w*|medicat\w*|dose|dosage|prescri\w*|disease|"
    r"cancer|diabet\w*|pain|sick|illness|triage|emergency room|suicid\w*|pregnan\w*|cure)\b",
    re.I)
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# Clause boundaries: sentence punctuation, or "and/also/plus" that starts a new question.
CLAUSE_SPLIT = re.compile(
    r"[?;!.]+|,?\s+(?:and|also|plus)\s+(?=(?:how|what|who|when|where|why|which|can|could|"
    r"do|does|is|are|will|should|tell)\b)", re.I)
# Words that carry no topic on their own; a clause made only of these is ignored.
FILLER = {"the", "a", "an", "is", "are", "my", "i", "do", "does", "can", "how", "what", "who",
          "to", "of", "for", "in", "on", "me", "you", "it", "be", "and", "or", "with", "also",
          "please", "tell", "about", "there", "this", "that", "your", "we", "us", "much"}

ABSTAIN_TEXT = "I don't have an approved answer for that. Please contact support."


@lru_cache
def corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text())


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _variants(word: str) -> set[str]:
    return {word, word + "s", word[:-1] if word.endswith("s") else word}


def _hits(words: list[str], term: str) -> bool:
    parts = term.split()
    if len(parts) == 1:
        return bool(_variants(term) & set(words))
    n = len(parts)
    return any(words[i:i + n] == parts for i in range(len(words) - n + 1))


def _group_hits(words: list[str], group: list[str]) -> list[str]:
    return [t for t in group if _hits(words, t)]


def _evaluate(words: list[str], entry: dict) -> tuple[bool, bool, int]:
    """(topic_hit, fully_supported, matched_term_count) for one entry."""
    per_group = [_group_hits(words, g) for g in entry["evidence"]]
    topic_hit = bool(per_group[0])
    supported = all(per_group)
    return topic_hit, supported, sum(len(h) for h in per_group)


def _abstain(reason: str, text: str = ABSTAIN_TEXT) -> dict:
    return {"abstained": True, "reason": reason, "answer": text, "sources": []}


def answer(question: str) -> dict:
    if BLOCKED.search(question):
        return _abstain("out_of_scope_clinical",
                        "I can't help with medical, diagnostic, or treatment questions. "
                        "Please contact a qualified healthcare professional.")
    words = _words(question)
    entries = corpus()["entries"]
    evaluated = [(e, *_evaluate(words, e)) for e in entries]
    with_topic = [x for x in evaluated if x[1]]
    supported = [x for x in evaluated if x[2]]
    if not supported:
        return _abstain("unsupported")
    if len(with_topic) > 1:
        # Two or more policy topics in one question: do not pick one silently.
        return _abstain("ambiguous_or_mixed_intent",
                        "Your question touches more than one topic. Please ask one thing at a time.")
    best, _, _, score = supported[0]
    for clause in CLAUSE_SPLIT.split(question):
        cw = _words(clause)
        groups_hit = [bool(_group_hits(cw, g)) for g in best["evidence"]]
        covered = groups_hit[0] or sum(groups_hit) >= 2
        if [w for w in cw if w not in FILLER] and not covered:
            # A clause with real content but no topic evidence for the chosen entry
            # (one generic phrase like "how many" is not evidence).
            return _abstain("ambiguous_or_mixed_intent",
                            "Part of your question is not covered by the approved FAQ. "
                            "Please ask one thing at a time.")
    return {"abstained": False, "reason": None, "answer": best["answer"],
            "sources": [{"id": best["id"], "title": best["title"], "score": score}]}
