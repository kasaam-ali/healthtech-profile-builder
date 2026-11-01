# Week 3 FAQ evaluation

Implementation: `backend/ml/faq.py`, a deterministic keyword matcher over the approved fictional corpus `backend/ml/faq_corpus.json` (8 entries). No network or paid API. A clinical intent regex forces abstention before retrieval; a minimum score of 2 is required to answer. Week 4 will upgrade to RAG with the same task prompt and abstention contract.

Automated: `backend/tests/test_week3_faq.py` (13 prompts plus 4 malformed bodies).

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

## Failures and refinements
- Early design scored only keyword hits, so "Based on my prediction, should I start treatment?" would match `prediction-meaning`. Refinement: clinical regex check runs first and always abstains.
- Plural/singular mismatch ("contacts" vs "contact") was handled by also matching the stripped or added trailing "s".
- Multi-word keywords ("how many", "sign in") are matched as phrases with weight 2.
- Known gap: synonyms not in the keyword list (e.g. "wipe my info") can abstain even though an answer exists. This is the safe failure mode; RAG in Week 4 should improve recall.
