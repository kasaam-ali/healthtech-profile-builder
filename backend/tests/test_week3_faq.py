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


@pytest.mark.parametrize("question,expected", CASES)
def test_faq_prompts(client, question, expected):
    r = client.post("/api/v1/faq", json={"question": question})
    assert r.status_code == 200
    d = r.json()
    assert "Not medical advice" in d["disclaimer"]
    if expected is None:
        assert d["abstained"] is True and d["sources"] == []
    else:
        assert d["abstained"] is False
        assert d["sources"][0]["id"] == expected


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "x" * 600}, {"q": "hi"}])
def test_faq_rejects_bad_body(client, body):
    assert client.post("/api/v1/faq", json=body).status_code == 422
