"""Tests for the embedding-based safety classifier.

They need the embedding model (about 220 MB, fetched once into models/fastembed) and the trained weights
(models/safety_clf.json). When either is missing the tests are skipped, and the product falls back to rules.
"""
import json

import pytest

from backend import ml_classifier

pytestmark = pytest.mark.skipif(
    not ml_classifier.ARTIFACT.exists() or not ml_classifier.CACHE_DIR.exists(),
    reason="embedding model or trained weights not present",
)


@pytest.fixture(autouse=True)
def enable_ml(monkeypatch):
    monkeypatch.setenv("SAFETY_ML", "1")
    ml_classifier.reset_for_tests()
    yield
    ml_classifier.reset_for_tests()


def test_artifact_is_consistent_with_model_and_has_all_intents():
    data = json.loads(ml_classifier.ARTIFACT.read_text(encoding="utf-8"))
    assert data["model"] == ml_classifier.MODEL_NAME
    for intent in ml_classifier.INTENTS:
        p = data["intents"][intent]
        assert len(p["coef"]) == 384 and 0.05 <= p["threshold"] <= 0.5


def test_paraphrases_unseen_by_the_rules_are_caught():
    from backend.intent_classifier import IntentClassifier
    clf = IntentClassifier()
    res = clf.classify_intent("Some days I wish I could just fall asleep and not wake up again")
    assert res["is_distress"] and res["target_tier"] == "T3"
    assert res["detected_by"]["model"] and "distress" not in res["detected_by"]["rules"]
    res_ar = clf.classify_intent("هل أخطب أو أتراجع عن الخطوبة، قرر لي")
    assert res_ar["is_decision_question"] and res_ar["handoff_message"]


def test_clearly_benign_messages_are_not_escalated():
    from backend.intent_classifier import IntentClassifier
    clf = IntentClassifier()
    for text in ("What time does the clinic open on Sunday?", "شكراً جزيلاً لكم", "How do I reset my password?"):
        assert clf.classify_intent(text)["detected_intents"] == [], text


def test_missing_weights_fall_back_to_rules_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(ml_classifier, "ARTIFACT", tmp_path / "nope.json")
    ml_classifier.reset_for_tests()
    from backend.intent_classifier import IntentClassifier
    res = IntentClassifier().classify_intent("I want to kill myself")
    assert res["is_distress"] is True and res["detected_by"]["model_available"] is False  # rules still protect


def test_router_marks_model_only_rules_and_never_lowers():
    from backend.database import Database
    from backend.triage_router import TriageRouter, TriageSignals
    import tempfile, os
    d = tempfile.mkdtemp()
    db = Database(f"sqlite:///{os.path.join(d, 't.db')}")
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('m1','a','M',1995,'F')")
    conn.commit(); conn.close()
    r = TriageRouter(db)
    d1 = r.evaluate(TriageSignals(person_id="m1", engine_category="screen_negative",
                                  user_message="Some days I wish I could just fall asleep and not wake up again"))
    assert d1.tier == "T3" and any(x.startswith("TRI-T3-003") and x.endswith("~ML") for x in d1.fired_rules)
    d2 = r.evaluate(TriageSignals(person_id="m1", engine_category="screen_negative", user_message="Thanks"))
    assert d2.tier == "T3"
