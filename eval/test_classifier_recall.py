"""Regression + honesty tests for the intent/safety classifier.

The labelled set in eval/safety_messages.py is a REGRESSION set (patterns were tuned on it), so 100% there
only guards against future breakage. Generalisation was measured on fresh, unseen messages and was poor
(about 2 of 17 on first contact; see docs/SAFETY_EVAL.md); that is why the product never treats an
unrecognised message as safe (`human_offer` is always true) and why an ML classifier is on the roadmap.
"""
from collections import defaultdict

from backend.intent_classifier import intent_classifier, normalize
from eval.safety_messages import MESSAGES, DISTRESS, COERCION, DECISION


def _recall(intent):
    items = [(t, e) for t, e in MESSAGES if intent in e]
    hits = sum(1 for t, _ in items if intent in intent_classifier.classify_intent(t)["detected_intents"])
    return hits, len(items)


def test_regression_recall_on_safety_intents_is_complete():
    for intent in (DISTRESS, COERCION, DECISION):
        hits, total = _recall(intent)
        assert hits == total, f"{intent}: {hits}/{total}"


def test_no_false_positives_on_benign_controls():
    for text, expected in MESSAGES:
        if not expected:
            assert intent_classifier.classify_intent(text)["detected_intents"] == [], text


def test_arabic_normalisation_variants_match():
    assert normalize("أريد أن أموتُ") == normalize("اريد ان اموت")
    for variant in ("هل نتزوّج؟", "هل نتزوج؟"):
        assert intent_classifier.classify_intent(variant)["is_decision_question"]


def test_chat_endpoint_routes_to_triage_stores_text_not_in_audit_and_offers_human():
    from fastapi.testclient import TestClient
    import backend.main as main_mod
    c = TestClient(main_mod.app)
    r = c.post("/api/chat/ask", json={"query": "I don't want to live anymore", "language": "en"}).json()
    assert r["triage"]["tier"] == "T3" and any(x.startswith("TRI-T3-003") for x in r["triage"]["fired_rules"])
    assert r["safety"]["emergency"][0]["number"] == "999" and r["human_offer"] is True
    unknown = c.post("/api/chat/ask", json={"query": "blorp zzz", "language": "en"}).json()
    assert unknown["recognised"] is False and unknown["human_offer"] is True and unknown["safety"] is None
    conn = main_mod.db.get_connection()
    leaked = conn.execute("SELECT COUNT(*) FROM audit_event WHERE target LIKE '%live anymore%'").fetchone()[0]
    conn.execute("DELETE FROM chat_message WHERE text IN ('blorp zzz', ?)", ("I don't want to live anymore",))
    conn.commit(); conn.close()
    assert leaked == 0
