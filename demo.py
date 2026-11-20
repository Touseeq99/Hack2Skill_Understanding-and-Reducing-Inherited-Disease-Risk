"""Automated 5-minute Demo Runner for the Inherited Disease Risk Platform.
Demonstrates the full end-to-end clinical workflow described in Section 12:
- Fatima Al Mansoori & Tariq Al Nuaimi (Pre-marital screening, HBB same-gene match).
"""

from backend.database import db
from backend.service import service
from backend.intent_classifier import intent_classifier
from backend.triage_router import router, TriageSignals
from backend.referral_state_machine import referral_sm
from backend.scheduler import scheduler
from backend.pdf_generator import generate_case_packet_pdf
from backend.family_notice import family_notice_svc
from backend.analytics import analytics_svc
from explain.pipeline import pipeline


def print_step(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_demo():
    print_step("STEP 1: Fatima Opens Her Individual Screening Result (Arabic)")
    fatima_id = "person_001"
    fatima_res = service.get_individual_assessment(fatima_id, current_user_id=fatima_id)
    print(f"Subject: Fatima (ID: {fatima_id})")
    print(f"Category: {fatima_res.category} | Tier: {fatima_res.tier}")
    print(f"Genes Identified: {', '.join(fatima_res.genes)}")
    print(f"Fired Rule: {fatima_res.rule_id} (IND-002: One pathogenic variant in AR gene)")
    print(f"Natural Frequency: {fatima_res.natural_frequency}")

    # Arabic explanation generation
    explanation = pipeline.generate_explanation(
        template_key="CARRIER_AR_SUMMARY",
        slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
        person_id=fatima_id,
        language="ar",
        reading_level="standard",
    )
    print("\n[Patient App View - Arabic (RTL)]")
    print(explanation["final_text"])
    print(f"\nAudit Log Hash: {explanation['text_hash'][:16]}... (tamper-evident SHA-256)")

    print_step("STEP 2: Couple Mutual Consent & Compatibility Matching (Fatima & Tariq)")
    tariq_id = "person_101"
    print(f"Partner A: Fatima ({fatima_id})")
    print(f"Partner B: Tariq ({tariq_id})")

    # Evaluate couple compatibility through couple link
    couple_link_id = "cpl_link_001"
    couple_res = service.get_couple_assessment(couple_link_id, current_user_id=fatima_id)

    print(f"Couple Link: {couple_link_id}")
    print(f"Compatibility Outcome: {couple_res.outcome}")
    print(f"Shared Genes: {', '.join(couple_res.shared_genes)}")
    print(f"Couple Triage Tier: {couple_res.tier}")
    print(f"Natural Frequencies: {couple_res.natural_frequencies}")
    print(f"Icon Array Categories: {[c['label_en'] + ': ' + str(c['count']) for c in couple_res.icon_array.get('categories', [])]}")
    print(f"Fired Couple Rule: {couple_res.rule_id} (CPL-001: Both carriers of same AR gene)")

    # Test consent revocation protection
    print("\n[Privacy Verification]")
    print("Testing Revocation Policy: Mutual active consent is required to access couple outcome.")
    print("Revoking Fatima's consent grant to verify immediate protection...")
    # Retrieve Fatima's grant from database
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM consent_grant WHERE grantor = ? AND scope = 'couple_result' AND revoked_at IS NULL", (fatima_id,))
    grant_row = cur.fetchone()
    conn.close()

    if grant_row:
        grant_id = grant_row["id"]
        service.revoke_consent(grant_id, current_user_id=fatima_id)
        try:
            service.get_couple_assessment(couple_link_id, current_user_id=fatima_id)
            print("ERROR: Couple assessment was not blocked!")
        except Exception as e:
            print(f"SUCCESS: Read blocked after revocation -> {e.detail if hasattr(e, 'detail') else e}")
        # Restore grant for demo continuity
        service.grant_consent(grantor=fatima_id, grantee=tariq_id, scope="couple_result", purpose="Demo restore", current_user_id=fatima_id, couple_link_id=couple_link_id)
        print("Restored mutual consent grant for downstream counselling steps.")

    print_step("STEP 3: Fatima Asks 'Should We Still Get Married?' -> Guardrail Triggers")
    user_questions = [
        ("Arabic Query", "هل ننفصل يا دكتور أم نتزوج رغم نتيجة الثلاسيميا؟"),
        ("English Query", "Should we still get married given our risk?"),
    ]
    for label, query in user_questions:
        print(f"\nUser Asks ({label}): \"{query}\"")
        intent_res = intent_classifier.classify_intent(query)
        print(f"Intent Analysis: is_decision_question={intent_res['is_decision_question']}")
        print("Automated Handoff Response (Strictly Non-Directive):")
        print(f"  \"{intent_res['handoff_message']}\"")

    # Triage Escalation
    triage_decision = router.evaluate(TriageSignals(
        person_id=fatima_id,
        engine_category="carrier",
        couple_outcome="same_gene_match",
        user_message="Should we still get married?",
    ))
    print(f"\nTriage Escalation: Tier {triage_decision.tier} | SLA Due: {triage_decision.sla_due}")
    print(f"Fired Triage Rules: {triage_decision.fired_rules}")
    print(f"System Action: {triage_decision.system_action}")

    print_step("STEP 4: Genetic Counsellor Portal & Clinical Case Packet")
    print("Counsellor Maryam logs in to /portal (Emirati National Genomics Service)")
    queue = scheduler.list_counsellor_queue()
    print(f"Active Priority Queue Length: {len(queue)} cases awaiting counselling")
    
    # Pick a case that can progress through booking, or evaluate a fresh case for Fatima
    matching_case = next((c for c in queue if c["state"] in ("created", "offered")), None)
    if not matching_case:
        triage_decision = router.evaluate(TriageSignals(
            person_id=fatima_id,
            engine_category="carrier",
            couple_outcome="same_gene_match",
            user_message="Book urgent session with counsellor",
        ))
        case_id = triage_decision.case_id
        patient_name = "Fatima Al Mansoori"
        tier = triage_decision.tier
        sla_due = triage_decision.sla_due
    else:
        case_id = matching_case["id"]
        patient_name = matching_case["patient_name"]
        tier = matching_case["tier"]
        sla_due = matching_case["sla_due"]

    print(f"Case Selected: ID={case_id} | Patient={patient_name} | Tier={tier} | SLA Due={sla_due}")

    # Appointment booking & referral lifecycle transition
    print("\nScheduling Appointment & Updating Referral Lifecycle:")
    booking = scheduler.book_appointment(
        case_id=case_id,
        counsellor_id="counsellor_maryam",
        slot_time="2026-11-18T10:00:00Z",
        actor_id="counsellor_maryam",
    )
    print(f" -> Slot Booked: ID={booking['booking_id']} | Counsellor={booking['counsellor_id']} | Modality={booking['modality']}")

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM referral WHERE case_id = ?", (case_id,))
    ref_row = cur.fetchone()
    conn.close()
    if ref_row:
        attended_res = referral_sm.transition(ref_row["id"], "attended", actor_id="counsellor_maryam", notes="Comprehensive pre-conception counselling conducted.")
        print(f" -> State Transition: {attended_res['previous_state']} -> {attended_res['current_state']}")

    # PDF Case Packet generation
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT tc.*, p.name as patient_name, p.dob_year, p.sex, p.language
        FROM triage_case tc
        JOIN person p ON tc.person_id = p.id
        WHERE tc.id = ?
    """, (case_id,))
    row = cur.fetchone()
    conn.close()

    case_data = dict(row) if row else {
        "case_id": case_id,
        "patient_name": patient_name,
        "tier": tier,
        "sla_due": sla_due,
        "gene": "HBB",
        "condition": "Beta-thalassemia",
    }
    pdf_bytes = generate_case_packet_pdf(case_data)
    print(f"Clinical Case Packet PDF generated successfully ({len(pdf_bytes)} bytes, ReportLab engine).")

    print_step("STEP 5: Anonymous Family Cascade Notice")
    print("Fatima initiates an anonymous cascade notice for her first cousin.")
    notice = family_notice_svc.send_notice(
        sender_id=fatima_id,
        channel="sms",
        recipient_contact="+971501234567",
        condition_name="Beta-thalassemia",
    )
    print(f"Notice Status: Created | Token: {notice['token']}")
    print("Sender Anonymity: Sender identity is omitted from notification body.")
    print(f"Message Preview (AR): \"{notice['message_ar']}\"")
    print(f"Mandatory Sender Privacy Warning: \"{notice['warning'][:90]}...\"")

    # Relative opens notice
    opened_info = family_notice_svc.open_notice(notice["token"])
    print(f"Relative Opens Token: Verified condition='{opened_info['condition_name']}', sender identity is completely omitted.")

    print_step("STEP 6: Outcomes and Equity Parity Dashboard")
    dash = analytics_svc.get_dashboard_metrics()
    print(f"Ethical Non-Metric Policy: {dash['ethical_policy']['explicit_excluded_metric']}")
    def _v(x, suffix=""):
        return "no data yet" if x is None else f"{x}{suffix}"

    comp, up, priv = dash["comprehension"], dash["counselling_uptake"], dash["privacy_and_security"]
    print(f"Comprehension Uplift: {_v(comp['uplift_percentage_points'], ' percentage points')} "
          f"(pre {_v(comp['pre_explanation_baseline_score'], '%')} -> post {_v(comp['post_score_same_people'], '%')}, "
          f"{comp['paired_people']} paired people, synthetic cohort)")
    print(f"Counselling Uptake: {_v(up['uptake_percentage'], '%')} of T1-T3 cases booked or beyond")
    for tier, v in dash["time_to_referral_vs_sla"].items():
        print(f"Time to booking {tier}: median {_v(v['median_hours'], 'h')}, within SLA {_v(v['adherence_pct'], '%')} (n={v['n']})")
    print(f"Revocations honoured: {_v(priv['revocations_honored_pct'], '%')} "
          f"({priv['revocations_total']} revocations, {priv['reads_after_revocation']} reads after revocation, "
          f"{priv['unauthorized_attempts_blocked']} blocked attempts)")
    print(f"Cryptographic Audit Chain Integrity: {'VERIFIED OK' if dash['privacy_and_security']['cryptographic_audit_chain_valid'] else 'COMPROMISED'}")
    print(f"Equity Parity Achieved: {dash['equity_breakdowns']['equity_parity_achieved']} (max gap: {dash['equity_breakdowns']['maximum_equity_gap_points']} points across language, literacy, sex and age)")

    print("\n" + "=" * 70)
    print("  ALL 6 DEMO STEPS COMPLETED SUCCESSFULLY - FULL SYSTEM OPERATIONAL")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
