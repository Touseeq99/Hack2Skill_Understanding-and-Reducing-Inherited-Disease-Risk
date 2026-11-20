import pytest
from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.analytics import AnalyticsService
from backend.database import Database
from backend.measures import score_measure
from backend.triage_router import TriageRouter, TriageSignals


def test_sure_and_gad2_scoring_cutoffs():
    assert score_measure("sure", [1, 1, 1, 1])["flag"] is False
    assert score_measure("sure", [1, 1, 1, 0])["flag"] is True  # <4 means decisional conflict
    assert score_measure("anxiety", [1, 1])["flag"] is False
    assert score_measure("anxiety", [2, 1])["flag"] is True     # >=3 positive screen


@pytest.mark.parametrize("measure,items", [("sure", [1, 1]), ("sure", [2, 0, 0, 0]), ("anxiety", [4, 0]), ("anxiety", [1]), ("bogus", [1])])
def test_invalid_items_rejected(measure, items):
    with pytest.raises(ValueError):
        score_measure(measure, items)


def test_measures_endpoint_scores_on_server_and_rejects_bad_phase():
    c = TestClient(main_mod.app)
    ok = c.post("/api/measures", json={"measure": "anxiety", "phase": "before_counselling", "items": [3, 3]})
    assert ok.status_code == 200 and ok.json()["flag"] is True and ok.json()["score"] == 6.0
    assert c.post("/api/measures", json={"measure": "anxiety", "phase": "nonsense", "items": [0, 0]}).status_code == 422
    # keep the shared demo database clean
    conn = main_mod.db.get_connection()
    conn.execute("DELETE FROM measure_response WHERE person_id = 'person_001' AND score = 6.0")
    conn.commit(); conn.close()


def test_positive_anxiety_screen_raises_to_t1_never_lowers(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'm.db'}")
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('m1','a','M',1995,'F')")
    conn.commit(); conn.close()
    r = TriageRouter(db)
    d = r.evaluate(TriageSignals(person_id="m1", engine_category="screen_negative", anxiety_screen_positive=True))
    assert d.tier == "T1" and "TRI-T1-005" in d.fired_rules
    d2 = r.evaluate(TriageSignals(person_id="m1", engine_category="screen_negative"))
    assert d2.tier == "T1"


def test_wellbeing_metrics_pair_and_do_not_invent(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'w.db'}")
    svc = AnalyticsService(database=db)
    empty = svc.get_dashboard_metrics()["wellbeing"]
    assert empty["sure"]["flag_pct_a"] is None and empty["anxiety"]["paired"] == 0

    conn = db.get_connection()
    for pid in ("w1", "w2"):
        conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?,?,?,1995,'F')", (pid, "a" + pid, pid))
    rows = [("w1", "sure", "after_explanation", 3, 1), ("w1", "sure", "after_counselling", 4, 0),
            ("w2", "sure", "after_explanation", 2, 1), ("w2", "sure", "after_counselling", 4, 0)]
    for i, (p, m, ph, sc, fl) in enumerate(rows):
        conn.execute("INSERT INTO measure_response (id, person_id, measure, phase, score, flag, items) VALUES (?,?,?,?,?,?, '[]')", (f"r{i}", p, m, ph, sc, fl))
    conn.commit(); conn.close()
    sure = svc.get_dashboard_metrics()["wellbeing"]["sure"]
    assert sure["flag_pct_a"] == 100.0 and sure["flag_pct_b"] == 0.0 and sure["paired"] == 2
