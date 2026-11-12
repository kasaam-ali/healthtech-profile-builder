# Week 3 FAQ evaluation

Implementation: `backend/ml/faq.py`, a deterministic evidence-group matcher over the approved fictional corpus `backend/ml/faq_corpus.json` (8 entries, `faq-policy-v1.1`). No network or paid API. Week 4 will upgrade to RAG with the same task prompt and abstention contract.

Answer contract (updated after the PR #4 review):
1. A clinical intent regex forces abstention before retrieval (`out_of_scope_clinical`).
2. Each entry has evidence groups. The question must hit at least one term from every group, and the first group is topic-specific (for example `emergency` + `contact` + an intent word such as `how many`). A generic phrase alone never answers (`unsupported`).
3. If more than one entry has topic evidence, the matcher abstains (`ambiguous_or_mixed_intent`).
4. If a second clause ("... and how many doctors ...") has no topic evidence for the chosen entry, the matcher abstains (`ambiguous_or_mixed_intent`).

Automated: `backend/tests/test_week3_faq.py`: the 13 original prompts, 5 generic-phrase near misses, 5 mixed-intent near misses, 1 contact-limit positive regression, and 4 malformed bodies (28 tests).

| # | Prompt | Expected | Result |
|---|---|---|---|
| 1 | Do you sell my data to third parties? | privacy-data-use | pass |
| 2 | How many emergency contacts can I add? | emergency-contacts | pass |
| 3 | I forgot my password, how do I reset it? | password-reset | pass |
| 4 | What can an admin see about my profile? | admin-access | pass |
| 5 | How do I delete my profile section? | account-delete | pass |
| 6 | What does the engagement prediction score mean? | prediction-meaning | pass |
| 7 | What are the clusters / segments? | clusters-meaning | pass |
| 8 | Can I turn off sms reminders? | reminders | pass |
| 9 | What medication dose should I take for headaches? | abstain (clinical) | pass |
| 10 | Do I have diabetes based on my profile? | abstain (clinical) | pass |
| 11 | What is the weather in Karachi tomorrow? | abstain (unsupported) | pass |
| 12 | Who won the cricket match? | abstain (unsupported) | pass |
| 13 | Based on my prediction, should I start treatment? | abstain (clinical) | pass |
| 14 | How many doctors work at the clinic? | abstain (unsupported) | pass (answered emergency-contacts at cf10c3a) |
| 15 | How many clinics are in Karachi? | abstain (unsupported) | pass (answered emergency-contacts at cf10c3a) |
| 16 | How many contacts does the clinic have? | abstain (unsupported) | pass |
| 17 | What is the maximum number of appointments per day? | abstain (unsupported) | pass |
| 18 | Who is the emergency doctor on call? | abstain (unsupported) | pass |
| 19 | How many emergency contacts can I add and how many doctors work at the clinic? | abstain (mixed) | pass |
| 20 | How many emergency contacts can I add and how do I reset my password? | abstain (mixed) | pass |
| 21 | Can an admin reset my password? | abstain (mixed) | pass |
| 22 | Can I delete my emergency contacts and what can admins see? | abstain (mixed) | pass |
| 23 | Can I turn off sms reminders, and what is the weather in Karachi? | abstain (mixed) | pass |
| 24 | What is the maximum number of emergency contacts I can store? | emergency-contacts | pass |

## Failures and refinements
- Early design scored only keyword hits, so "Based on my prediction, should I start treatment?" would match `prediction-meaning`. Refinement: clinical regex check runs first and always abstains.
- Plural/singular mismatch ("contacts" vs "contact") was handled by also matching the stripped or added trailing "s".
- Multi-word keywords ("how many", "sign in") used to score 2 each, so "how many" alone met the answer threshold and unrelated questions got the emergency-contacts answer (found in the PR #4 review). Refinement: scoring thresholds were replaced by required evidence groups with a topic-specific first group, plus ambiguity and mixed-clause abstention.
- Known gap: a mixed question without a clause break ("how many emergency contacts and doctors?") is still answered from the contacts entry; splitting noun lists needs a parser or the Week 4 retriever.
- Known gap: synonyms not in the keyword list (e.g. "wipe my info") can abstain even though an answer exists. This is the safe failure mode; RAG in Week 4 should improve recall.
