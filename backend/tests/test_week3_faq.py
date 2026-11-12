import pytest

# (question, expected source id or None for abstention)
CASES = [
    ("Do you sell my data to third parties?", "privacy-data-use"),
    ("How many emergency contacts can I add?", "emergency-contacts"),
    ("I forgot my password, how do I reset it?", "password-reset"),
    ("What can an admin see about my profile?", "admin-access"),
    ("How do I delete my profile section?", "account-delete"),
    ("What does the engagement prediction score mean?", "prediction-meaning"),
    ("What are the clusters / segments?", "clusters-meaning"),
    ("Can I turn off sms reminders?", "reminders"),
    ("What medication dose should I take for headaches?", None),
    ("Do I have diabetes based on my profile?", None),
    ("What is the weather in Karachi tomorrow?", None),
    ("Who won the cricket match?", None),
    ("Based on my prediction, should I start treatment?", None),
]

# PR #4 review: generic phrases like "how many" must not answer on their own.
UNSUPPORTED_GENERIC = [
    "How many doctors work at the clinic?",
    "How many clinics are in Karachi?",
    "How many contacts does the clinic have?",
    "What is the maximum number of appointments per day?",
    "Who is the emergency doctor on call?",
]

# Near misses that mix a supported topic with another topic or an unsupported clause.
MIXED_INTENT = [
    "How many emergency contacts can I add and how many doctors work at the clinic?",
    "How many emergency contacts can I add and how do I reset my password?",
    "Can an admin reset my password?",
    "Can I delete my emergency contacts and what can admins see?",
    "Can I turn off sms reminders, and what is the weather in Karachi?",
]


def _ask(client, q):
    r = client.post("/api/v1/faq", json={"question": q})
    assert r.status_code == 200
    d = r.json()
    assert "Not medical advice" in d["disclaimer"]
    return d


@pytest.mark.parametrize("question,expected", CASES)
def test_faq_prompts(client, question, expected):
    d = _ask(client, question)
    if expected is None:
        assert d["abstained"] is True and d["sources"] == []
    else:
        assert d["abstained"] is False
        assert d["sources"][0]["id"] == expected


@pytest.mark.parametrize("question", UNSUPPORTED_GENERIC)
def test_generic_phrase_alone_abstains(client, question):
    d = _ask(client, question)
    assert d["abstained"] is True, d
    assert d["reason"] == "unsupported"
    assert d["sources"] == []
    assert "5 emergency contacts" not in d["answer"]


@pytest.mark.parametrize("question", MIXED_INTENT)
def test_mixed_intent_abstains(client, question):
    d = _ask(client, question)
    assert d["abstained"] is True, d
    assert d["reason"] == "ambiguous_or_mixed_intent"
    assert d["sources"] == []


def test_contact_limit_still_answered(client):
    # Positive regression: the supported contact-limit question keeps its answer and source.
    d = _ask(client, "What is the maximum number of emergency contacts I can store?")
    assert d["abstained"] is False
    assert d["sources"][0]["id"] == "emergency-contacts"
    assert "up to 5 emergency contacts" in d["answer"]


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "x" * 600}, {"q": "hi"}])
def test_faq_rejects_bad_body(client, body):
    assert client.post("/api/v1/faq", json=body).status_code == 422
