import pytest
from fastapi import HTTPException
from backend.intent_classifier import IntentClassifier
from backend.triage_router import TriageRouter, TriageSignals
from backend.referral_state_machine import ReferralStateMachine
from backend.scheduler import SchedulerService
from backend.pdf_generator import generate_case_packet_pdf
from backend.family_notice import FamilyNoticeService
from backend.database import Database


@pytest.fixture
def p3_ctx(tmp_path):
    db_file = tmp_path / "p3_test.db"
    db = Database(f"sqlite:///{db_file}")

    # Seed test person
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('p_test', 'auth_test', 'Fatima', 1998, 'F')")
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('p_minor', 'auth_minor', 'Minor User', 2010, 'F')")
    conn.commit()
    conn.close()

    router = TriageRouter(db)
    rsm = ReferralStateMachine(db)
    sched = SchedulerService(db)
    fns = FamilyNoticeService(db)

    return {
        "db": db,
        "router": router,
        "referral_sm": rsm,
        "scheduler": sched,
        "family_notice": fns,
    }


def test_intent_classifier_decision_question_and_safety():
    clf = IntentClassifier()

    # English decision question: must produce non-directive handoff and target T2
    res_en = clf.classify_intent("Should we still get married after this result?", language="en")
    assert res_en["is_decision_question"] is True
    assert res_en["target_tier"] == "T2"
    assert res_en["handoff_message"] is not None
    assert "never advise on personal relationship" in res_en["handoff_message"]

    # Arabic decision question
    res_ar = clf.classify_intent("هل نتزوج يا دكتور؟ ماذا تنصحنا؟", language="ar")
    assert res_ar["is_decision_question"] is True
    assert res_ar["target_tier"] == "T2"
    assert res_ar["handoff_message"] is not None
    assert "لا نقدم إطلاقاً أي نصيحة بالزواج" in res_ar["handoff_message"]

    # Distress language -> T3
    res_distress = clf.classify_intent("I want to kill myself, I feel hopeless")
    assert res_distress["is_distress"] is True
    assert res_distress["target_tier"] == "T3"

    # Coercion language -> T3
    res_coercion = clf.classify_intent("أنا مجبورة ومغصوبة على الزواج وخائفة منه")
    assert res_coercion["is_coercion"] is True
    assert res_coercion["target_tier"] == "T3"


def test_triage_router_rules_and_no_downgrade(p3_ctx):
    router = p3_ctx["router"]

    # 1. Screen negative -> T0
    dec_t0 = router.evaluate(TriageSignals(person_id="p_test", engine_category="screen_negative"))
    assert dec_t0.tier == "T0"
    assert "TRI-T0-001" in dec_t0.fired_rules

    # 2. Teach-back failed twice -> T1
    dec_t1 = router.evaluate(TriageSignals(person_id="p_test", engine_category="carrier", teach_back_failed_twice=True))
    assert dec_t1.tier == "T1"
    assert "TRI-T1-002" in dec_t1.fired_rules
    assert dec_t1.sla_due is not None  # 10 days

    # 3. Same gene match -> T2
    dec_t2 = router.evaluate(TriageSignals(person_id="p_test", engine_category="carrier", couple_outcome="same_gene_match"))
    assert dec_t2.tier == "T2"
    assert "TRI-T2-001" in dec_t2.fired_rules

    # 4. Decision question asked -> T2
    dec_dq = router.evaluate(TriageSignals(person_id="p_test", engine_category="carrier", user_message="Should we still marry?"))
    assert dec_dq.tier == "T2"
    assert any(r.startswith("TRI-T2-005") for r in dec_dq.fired_rules)
    assert dec_dq.directive_handoff_message is not None

    # 5. Minor under 18 -> T3
    dec_minor = router.evaluate(TriageSignals(person_id="p_minor", age_years=16))
    assert dec_minor.tier == "T3"
    assert "TRI-T3-005" in dec_minor.fired_rules

    # 6. Same gene match AND pregnant -> T3
    dec_preg = router.evaluate(TriageSignals(person_id="p_test", engine_category="carrier", couple_outcome="same_gene_match", is_pregnant=True))
    assert dec_preg.tier == "T3"
    assert "TRI-T3-002" in dec_preg.fired_rules

    # 7. Distress language in message -> T3
    dec_dist = router.evaluate(TriageSignals(person_id="p_test", user_message="I want to end my life"))
    assert dec_dist.tier == "T3"
    assert any(r.startswith("TRI-T3-003") for r in dec_dist.fired_rules)

    # 8. HARD RULE: Tiers never auto-downgrade!
    # If existing case was T2, an event that triggers T0 must remain T2!
    # (p_test already holds a persisted T3 case from earlier steps, so use a fresh person
    # to exercise the caller-supplied existing_case_tier path.)
    conn = p3_ctx["db"].get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('p_fresh', 'auth_fresh', 'Fresh', 1995, 'F')")
    conn.commit()
    conn.close()
    dec_no_downgrade = router.evaluate(TriageSignals(person_id="p_fresh", engine_category="screen_negative", existing_case_tier="T2"))
    assert dec_no_downgrade.tier == "T2"


def test_referral_state_machine_flow(p3_ctx):
    rsm = p3_ctx["referral_sm"]
    db = p3_ctx["db"]

    # Create dummy case
    conn = db.get_connection()
    cur = conn.cursor()
    case_id = "case_flow_test"
    cur.execute("INSERT INTO triage_case (id, person_id, tier, state) VALUES (?, 'p_test', 'T2', 'created')", (case_id,))
    conn.commit()
    conn.close()

    # Create referral
    ref = rsm.create_referral(case_id=case_id, service_id="counselling", actor_id="counsellor_01")
    ref_id = ref["referral_id"]
    assert ref["state"] == "created"

    # Step: created -> booked
    res_book = rsm.transition(ref_id, "booked", actor_id="counsellor_01")
    assert res_book["current_state"] == "booked"

    # Step: booked -> attended
    res_att = rsm.transition(ref_id, "attended", actor_id="counsellor_01")
    assert res_att["current_state"] == "attended"

    # Step: attended -> confirmatory_ordered
    res_conf = rsm.transition(ref_id, "confirmatory_ordered", actor_id="counsellor_01")
    assert res_conf["current_state"] == "confirmatory_ordered"

    # Step: confirmatory_ordered -> confirmatory_resulted
    res_res = rsm.transition(ref_id, "confirmatory_resulted", actor_id="counsellor_01")
    assert res_res["current_state"] == "confirmatory_resulted"

    # Step: confirmatory_resulted -> specialist_referred
    res_spec = rsm.transition(ref_id, "specialist_referred", actor_id="counsellor_01")
    assert res_spec["current_state"] == "specialist_referred"

    # Step: specialist_referred -> specialist_seen
    res_seen = rsm.transition(ref_id, "specialist_seen", actor_id="counsellor_01")
    assert res_seen["current_state"] == "specialist_seen"

    # Step: specialist_seen -> closed
    res_close = rsm.transition(ref_id, "closed", actor_id="counsellor_01")
    assert res_close["current_state"] == "closed"

    # Invalid transition from closed -> raises HTTPException 400!
    with pytest.raises(HTTPException) as exc:
        rsm.transition(ref_id, "booked", actor_id="counsellor_01")
    assert exc.value.status_code == 400


def test_internal_scheduler_and_queue(p3_ctx):
    sched = p3_ctx["scheduler"]
    db = p3_ctx["db"]

    conn = db.get_connection()
    cur = conn.cursor()
    case_id = "case_sched_test"
    cur.execute("INSERT INTO triage_case (id, person_id, tier, state) VALUES (?, 'p_test', 'T2', 'offered')", (case_id,))
    conn.commit()
    conn.close()

    booking = sched.book_appointment(
        case_id=case_id,
        counsellor_id="counsellor_dr_layla",
        slot_time="2026-11-20T10:00:00Z",
        language_pref="ar",
        modality="video",
    )
    assert booking["status"] == "booked"
    assert booking["counsellor_id"] == "counsellor_dr_layla"

    # Check queue returns case
    queue = sched.list_counsellor_queue(counsellor_id="counsellor_dr_layla")
    case_ids = [c["id"] for c in queue]
    assert case_id in case_ids


def test_pdf_packet_generation():
    case_data = {
        "case_id": "case_pdf_01",
        "patient_name": "Fatima Al Mansoori",
        "dob_year": 1998,
        "sex": "F",
        "language": "Arabic",
        "tier": "T2",
        "sla_due": "Within 3 days",
        "assigned_to": "Dr. Layla",
        "state": "Booked",
        "fired_rules": ["TRI-T2-001"],
        "finding_type": "Carrier",
        "gene": "HBB",
        "condition": "Beta-thalassemia",
        "quiz_score": 100.0,
    }
    pdf_bytes = generate_case_packet_pdf(case_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_anonymous_family_notice_flow(p3_ctx):
    fns = p3_ctx["family_notice"]

    # Send anonymous notice
    res = fns.send_notice(
        sender_id="p_test",
        channel="whatsapp",
        condition_name="Beta-thalassemia",
        recipient_contact="+971501112233",
    )
    assert res["sender_identity_disclosed"] is False
    assert "p_test" not in res["message_en"]
    assert "p_test" not in res["message_ar"]
    assert "Fatima" not in res["message_en"]
    assert "Notice: Depending on which relatives" in res["warning"] or "Privacy Notice" in res["warning"]

    # Open notice via token
    opened = fns.open_notice(res["token"])
    assert opened["status"] == "valid"
    assert opened["condition_name"] == "Beta-thalassemia"



def test_triage_never_downgrades_across_calls_and_upserts(p3_ctx):
    """DB-persisted case tier survives later benign evaluations; no duplicate cases."""
    router = p3_ctx["router"]
    db = p3_ctx["db"]

    high = router.evaluate(TriageSignals(person_id="p_test", engine_category="possible_affected", is_pregnant=True))
    assert high.tier == "T3"

    low = router.evaluate(TriageSignals(person_id="p_test", engine_category="screen_negative"))
    assert low.tier == "T3"
    assert low.case_id == high.case_id  # upsert, not a new case
    assert "TRI-T3-001" in low.fired_rules  # prior rule IDs are preserved for audit

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n, MAX(tier) AS t FROM triage_case WHERE person_id = 'p_test'")
    row = cur.fetchone()
    conn.close()
    assert row["n"] == 1 and row["t"] == "T3"
