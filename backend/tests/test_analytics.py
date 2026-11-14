"""Unit tests for Outcomes and Equity Analytics Service."""

import pytest
from backend.database import Database
from backend.analytics import AnalyticsService


@pytest.fixture
def analytics_test_db(tmp_path):
    db_file = tmp_path / "test_analytics.db"
    db_instance = Database(f"sqlite:///{db_file}")
    conn = db_instance.get_connection()
    cur = conn.cursor()

    # Seed test persons
    cur.execute("""
        INSERT INTO person (id, auth_id, name, language, literacy_pref, dob_year, sex, pregnancy_status)
        VALUES 
            ('p1', 'a1', 'Amna', 'ar', 'standard', 1995, 'F', 0),
            ('p2', 'a2', 'Saeed', 'ar', 'simple', 1992, 'M', 0),
            ('p3', 'a3', 'John', 'en', 'standard', 1988, 'M', 0),
            ('p4', 'a4', 'Fatima', 'ar', 'audio', 2010, 'F', 0)
    """)

    # Seed comprehension responses
    cur.execute("""
        INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language)
        VALUES 
            ('c1', 'p1', 'quiz_1', 'post', 100.0, '{}', 'ar'),
            ('c2', 'p2', 'quiz_1', 'post', 90.0, '{}', 'ar'),
            ('c3', 'p3', 'quiz_1', 'post', 95.0, '{}', 'en'),
            ('c4', 'p4', 'quiz_1', 'post', 90.0, '{}', 'ar')
    """)

    # Seed triage cases
    cur.execute("""
        INSERT INTO triage_case (id, person_id, tier, state, fired_rules, sla_due)
        VALUES 
            ('tc1', 'p1', 'T2', 'booked', '["IND-002"]', '2026-11-20'),
            ('tc2', 'p2', 'T1', 'created', '["IND-002"]', '2026-11-25'),
            ('tc3', 'p4', 'T3', 'attended', '["TRI-T3-004"]', '2026-11-15')
    """)

    # Seed family notices
    cur.execute("""
        INSERT INTO family_notice (id, sender_id_hash, channel, condition_name, token, opened, booked)
        VALUES ('fn1', 'hash123', 'sms', 'Beta-thalassemia', 'tok1', 1, 1)
    """)

    conn.commit()
    conn.close()
    return db_instance


def test_analytics_metrics_computation(analytics_test_db):
    svc = AnalyticsService(database=analytics_test_db)
    metrics = svc.get_dashboard_metrics()

    # Ethical policy checks
    assert metrics["ethical_policy"]["non_directive_principle"] is True
    assert "STRICTLY NOT" in metrics["ethical_policy"]["explicit_excluded_metric"]

    # Comprehension uplift
    assert metrics["comprehension"]["post_explanation_avg_score"] == pytest.approx(93.8, rel=1e-1)
    assert metrics["comprehension"]["uplift_percentage_points"] > 40.0

    # Counselling uptake
    assert metrics["counselling_uptake"]["t1_t2_t3_cases_total"] == 3
    assert metrics["counselling_uptake"]["booked_and_attended_count"] == 2
    assert metrics["counselling_uptake"]["uptake_percentage"] == pytest.approx(66.7, rel=1e-1)

    # Privacy
    assert metrics["privacy_and_security"]["unauthorized_access_breaches"] == 0
    assert metrics["privacy_and_security"]["revocations_honored_instantaneous_pct"] == 100.0

    # Equity parity
    assert "by_language" in metrics["equity_breakdowns"]
    assert "by_literacy_preference" in metrics["equity_breakdowns"]
    assert "by_sex" in metrics["equity_breakdowns"]
    assert "by_age_band" in metrics["equity_breakdowns"]
    assert metrics["equity_breakdowns"]["equity_parity_achieved"] is True
