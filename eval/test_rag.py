"""FAQ library and retrieval tests. Retrieval tests need the embedding model and are skipped without it."""
import re

import pytest

from backend import ml_classifier, rag
from explain.faq_library import FAQ, SUFFIX, with_suffix
from explain.validator import validator

PRICE_OR_HOURS = re.compile(r"(AED|dirham|درهم|\bprice\b|\bcost\b|opening hours|ساعات العمل|\d{1,2}\s?(am|pm)\b)", re.IGNORECASE)
DIRECTIVE = re.compile(r"\b(you should|you must|we recommend|you ought)\b|يجب عليك|ننصحك", re.IGNORECASE)


def test_every_block_is_complete_and_non_directive():
    ids = [f["id"] for f in FAQ]
    assert len(ids) == len(set(ids))
    for f in FAQ:
        for lang in ("en", "ar"):
            assert len(f["q"][lang]) >= 3 and f["a"][lang]
            text = with_suffix(f["a"][lang], lang)
            ok, errors, _ = validator.validate(text, source_template=text, language=lang)
            assert ok, (f["id"], lang, errors)          # banned phrases, disclaimers, numbers
            assert not PRICE_OR_HOURS.search(text), (f["id"], "states a fact the platform does not hold")
            assert not DIRECTIVE.search(text), (f["id"], "directive wording")
    assert "screening result, not a diagnosis" in SUFFIX["en"]


needs_model = pytest.mark.skipif(not ml_classifier.CACHE_DIR.exists(), reason="embedding model not present")


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "1")
    rag.reset_for_tests()
    yield
    rag.reset_for_tests()


@needs_model
def test_clear_question_returns_the_approved_block_verbatim(enabled):
    a = rag.answer("What does being a carrier mean?", "en")
    assert a and a["id"] == "carrier_meaning"
    assert a["text"] == with_suffix(next(f for f in FAQ if f["id"] == "carrier_meaning")["a"]["en"], "en")


@needs_model
def test_out_of_scope_questions_get_no_answer(enabled):
    for q in ("How much does the test cost?", "What is the capital of France?", "Write me a poem"):
        assert rag.answer(q, "en") is None, q


@needs_model
def test_chat_endpoint_answers_education_but_not_risk_or_decision(enabled):
    from fastapi.testclient import TestClient
    import backend.main as main_mod
    c = TestClient(main_mod.app)
    ok = c.post("/api/chat/ask", json={"query": "Does being a carrier mean I am sick?", "language": "en"}).json()
    assert ok["answer"] and ok["answer"]["source"] == "approved_faq_v1"
    risky = c.post("/api/chat/ask", json={"query": "I want to kill myself", "language": "en"}).json()
    assert risky["answer"] is None and risky["safety"]
    decision = c.post("/api/chat/ask", json={"query": "Should we still get married?", "language": "en"}).json()
    assert decision["answer"] is None and decision["handoff_message"]
    conn = main_mod.db.get_connection()
    conn.execute("DELETE FROM chat_message WHERE person_id = 'person_001'")
    conn.commit(); conn.close()


def test_disabled_or_unavailable_returns_none(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "0")
    assert rag.answer("What does being a carrier mean?", "en") is None
