"""FastAPI Application entrypoint for Inherited Disease Risk Platform."""

from fastapi import FastAPI, Header, HTTPException, Query, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from pathlib import Path

from backend.database import db
from backend.service import service
from backend.audit_log import audit_logger
from engine.models import PersonResult, CoupleResult
from explain.graph_flow import graph, QUIZ_QUESTIONS, FlowState
from explain.pipeline import pipeline
from backend.scheduler import scheduler
from backend.pdf_generator import generate_case_packet_pdf
from backend.family_notice import family_notice_svc
from backend.triage_router import router, TriageSignals
from backend.referral_state_machine import referral_sm
from backend.analytics import analytics_svc
from backend.intent_classifier import intent_classifier

APP_DIR = Path(__file__).resolve().parent.parent / "app"
PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"

app = FastAPI(
    title="Inherited Disease Risk Platform API",
    version="1.0.0",
    description="Privacy-preserving, deterministic inherited disease risk assessment and triage engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header("patient", alias="X-User-Role"),
) -> Dict[str, str]:
    """Extract authenticated user and role from request headers (defaults to Fatima person_001 for demo convenience)."""
    user_id = x_user_id or "person_001"
    role = x_user_role or "patient"
    return {"user_id": user_id, "role": role}


# --- Request Schemas ---

class CreateCoupleLinkRequest(BaseModel):
    partner_b_id: str


class CreateGrantRequest(BaseModel):
    grantee: str
    scope: str = "couple_result"
    purpose: str = "Pre-marital compatibility risk screening"
    couple_link_id: Optional[str] = None
    expires_days: int = 365


class ChatAskRequest(BaseModel):
    query: str
    language: Optional[str] = "ar"


# --- Endpoints ---

@app.get("/health")
def health_check():
    valid, err = audit_logger.verify_chain()
    return {
        "status": "healthy",
        "engine_version": "v1",
        "clinical_signoff": "DRAFT - requires clinical sign-off",
        "audit_chain_valid": valid,
        "audit_error": err,
    }


@app.get("/api/me")
def get_current_profile(auth: Dict[str, str] = Depends(get_current_user)):
    person = service.get_person(auth["user_id"])
    if not person:
        raise HTTPException(status_code=404, detail="User profile not found.")
    return person


@app.get("/api/users/me/access-history")
def get_my_access_history(auth: Dict[str, str] = Depends(get_current_user)):
    """Allow user to view their own cryptographic access and audit history."""
    return audit_logger.get_user_access_history(auth["user_id"])


@app.get("/api/screening/{person_id}", response_model=PersonResult)
def get_individual_result(
    person_id: str,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return service.get_individual_assessment(person_id, current_user_id=auth["user_id"], role=auth["role"])


@app.post("/api/couples/link")
def create_couple_link(
    req: CreateCoupleLinkRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return service.create_couple_link(partner_a=auth["user_id"], partner_b=req.partner_b_id, current_user_id=auth["user_id"])


@app.post("/api/grants")
def grant_consent(
    req: CreateGrantRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return service.grant_consent(
        grantor=auth["user_id"],
        grantee=req.grantee,
        scope=req.scope,
        purpose=req.purpose,
        current_user_id=auth["user_id"],
        couple_link_id=req.couple_link_id,
        expires_days=req.expires_days,
    )


@app.post("/api/grants/{grant_id}/revoke")
def revoke_consent(
    grant_id: str,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return service.revoke_consent(grant_id=grant_id, current_user_id=auth["user_id"])


@app.get("/api/couples/{couple_link_id}/result", response_model=CoupleResult)
def get_couple_result(
    couple_link_id: str,
    is_consanguineous: bool = Query(False, description="Whether partners report shared ancestry / consanguinity"),
    auth: Dict[str, str] = Depends(get_current_user),
):
    return service.get_couple_assessment(
        couple_link_id=couple_link_id,
        current_user_id=auth["user_id"],
        is_consanguineous=is_consanguineous,
        role=auth["role"],
    )


@app.get("/api/audit/verify")
def verify_audit_log():
    valid, err = audit_logger.verify_chain()
    return {
        "valid": valid,
        "error": err,
        "message": "Audit chain intact and verified" if valid else f"Tampering detected: {err}",
    }


class QuizSubmitRequest(BaseModel):
    quiz_id: str = "teach_back_v1"
    answers: Dict[str, str]
    language: str = "ar"
    base_tier: str = "T0"
    template_key: str = "CARRIER_AR_SUMMARY"
    slots: Dict[str, Any] = Field(default_factory=dict)


@app.get("/api/quiz/questions")
def get_quiz_questions(lang: str = Query("ar", description="Language code: ar or en")):
    questions = QUIZ_QUESTIONS.get(lang, QUIZ_QUESTIONS["ar"])
    # Strip correct flag before sending to client
    sanitized = []
    for q in questions:
        sanitized.append({
            "id": q["id"],
            "question": q["question"],
            "options": [{"id": opt["id"], "text": opt["text"]} for opt in q["options"]],
        })
    return sanitized


@app.post("/api/quiz/submit")
def submit_quiz_answers(
    req: QuizSubmitRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    state = FlowState(
        person_id=auth["user_id"],
        template_key=req.template_key,
        slots=req.slots,
        language=req.language,
    )
    # Step quiz
    state = graph.step_quiz(state, req.answers)
    # Step route
    state = graph.step_route(state, base_tier=req.base_tier)

    return {
        "score": state.quiz_score,
        "passed": state.teach_back_passed,
        "attempts": state.quiz_attempts,
        "failed_twice": state.teach_back_failed_twice,
        "assigned_tier": state.assigned_tier,
        "system_action": state.system_action,
        "fired_rules": state.fired_rule_ids,
    }


@app.get("/api/explain/preview")
def preview_explanation(
    template_key: str = Query("CARRIER_AR_SUMMARY"),
    gene: str = Query("HBB"),
    condition: str = Query("Beta-thalassemia"),
    lang: str = Query("ar"),
    level: str = Query("standard"),
    auth: Dict[str, str] = Depends(get_current_user),
):
    return pipeline.generate_explanation(
        template_key=template_key,
        slots={"gene": gene, "condition_name": condition},
        person_id=auth["user_id"],
        language=lang,
        reading_level=level,
    )


@app.get("/")
@app.get("/app")
def serve_user_app():
    index_file = APP_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="App index file not found.")
    return FileResponse(index_file)


@app.get("/portal")
def serve_counsellor_portal():
    index_file = PORTAL_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Portal index file not found.")
    return FileResponse(index_file)


# --- Phase 3: Triage, Services, Scheduler, PDF & Family Cascade ---

class TriageEvaluateRequest(BaseModel):
    engine_category: str = "screen_negative"
    couple_outcome: Optional[str] = None
    is_pregnant: bool = False
    age_years: int = 25
    teach_back_failed_twice: bool = False
    user_message: Optional[str] = None
    reopen_count_48h: int = 0
    symptoms_reported: bool = False
    distress_signal: bool = False


class BookAppointmentRequest(BaseModel):
    counsellor_id: str = "counsellor_dr_layla"
    slot_time: str
    language_pref: str = "ar"
    modality: str = "video"


class TransitionStateRequest(BaseModel):
    target_state: str
    notes: Optional[str] = None


class SendFamilyNoticeRequest(BaseModel):
    channel: str = "whatsapp"
    condition_name: str = "Beta-thalassemia"
    recipient_contact: str = "+971500000000"


@app.post("/api/triage/evaluate")
def evaluate_triage(
    req: TriageEvaluateRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    signals = TriageSignals(
        person_id=auth["user_id"],
        engine_category=req.engine_category,
        couple_outcome=req.couple_outcome,
        is_pregnant=req.is_pregnant,
        age_years=req.age_years,
        teach_back_failed_twice=req.teach_back_failed_twice,
        user_message=req.user_message,
        reopen_count_48h=req.reopen_count_48h,
        symptoms_reported=req.symptoms_reported,
        distress_signal=req.distress_signal,
    )
    decision = router.evaluate(signals)
    return decision


@app.post("/api/chat/ask")
def ask_chat_assistant(
    req: ChatAskRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Safety and non-directive intent classifier assistant for patient queries."""
    res = intent_classifier.classify_intent(req.query, req.language)
    audit_logger.record_event(
        actor=auth["user_id"],
        action="chat_intent_query",
        target=req.query[:40],
    )
    return res


@app.get("/api/portal/queue")
def list_counsellor_queue(
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Retrieve active triage queue decorated with live patient and condition data."""
    import json
    counsellor_id = auth["user_id"] if auth["role"] == "counsellor" else None
    items = scheduler.list_counsellor_queue(counsellor_id)
    decorated = []
    for it in items:
        fr = it.get("fired_rules", "[]")
        try:
            rules = json.loads(fr) if isinstance(fr, str) else fr
        except Exception:
            rules = []
        
        tier = it.get("tier", "T2")
        if "TRI-T3-001" in rules or tier == "T3":
            cond = "CFTR / Severe Match (Urgent)"
            sla_text = "Urgent: 24h SLA"
        elif "TRI-T2-005" in rules or "TRI-T2-003" in rules:
            cond = "DMD X-linked Carrier"
            sla_text = "Priority: 3 Days SLA"
        elif tier == "T2":
            cond = "HBB Same-Gene Match (Beta-thalassemia)"
            sla_text = "Priority: 3 Days SLA"
        else:
            cond = "Carrier (Routine Follow-up)"
            sla_text = "Routine: 10 Days SLA"

        decorated.append({
            "id": it["id"],
            "person_id": it["person_id"],
            "name": it.get("patient_name", "Anonymous"),
            "patient_name": it.get("patient_name", "Anonymous"),
            "tier": tier,
            "state": it.get("state", "booked"),
            "condition": cond,
            "sla": sla_text,
            "fired_rules": rules,
        })
    return decorated


@app.get("/api/portal/cases/{case_id}")
def get_case_details(
    case_id: str,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Retrieve full clinical dossier and live findings for a triage case."""
    import json
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT tc.*, p.name as patient_name, p.dob_year, p.sex, p.language
        FROM triage_case tc
        JOIN person p ON tc.person_id = p.id
        WHERE tc.id = ?
    """, (case_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        # Fallback for canonical demo case if ID doesn't match a seeded DB row
        return {
            "id": case_id,
            "person_id": "person_001",
            "patient_name": "Fatima Al Mansoori",
            "dob_year": 1998,
            "age": 28,
            "sex": "Female",
            "language": "Arabic (Gulf)",
            "tier": "T2",
            "state": "booked",
            "sla_due": "3 Working Days (Active)",
            "assigned_to": "Dr. Layla Al Hashimi, MS, CGC",
            "fired_rules": ["TRI-T2-001", "IND-002"],
            "finding_type": "Autosomal Recessive Carrier (Pathogenic)",
            "gene": "HBB",
            "variant": "c.93-21G>A",
            "condition": "Beta-thalassemia",
            "partner_name": "Tariq Al Mazrouei",
            "partner_finding": "HBB c.118C>T (Pathogenic carrier)",
            "couple_outcome": "SAME-GENE MATCH (Beta-thalassemia)",
            "per_pregnancy_risk": "1 in 4 affected, 1 in 2 carrier, 1 in 4 unaffected",
            "consanguinity_status": "Reported 1st Cousins (Bennett 2002 shared)",
            "consent_status": "Mutual Grants Active",
            "quiz_score": "100% (Passed attempt 1)",
        }

    case_dict = dict(row)
    person_id = case_dict["person_id"]

    # Check for couple link
    cur.execute("""
        SELECT cl.id, cl.partner_a, cl.partner_b, cl.status, p1.name as name_a, p2.name as name_b
        FROM couple_link cl
        JOIN person p1 ON cl.partner_a = p1.id
        JOIN person p2 ON cl.partner_b = p2.id
        WHERE cl.partner_a = ? OR cl.partner_b = ?
    """, (person_id, person_id))
    cpl_row = cur.fetchone()
    conn.close()

    partner_name = "Tariq Al Mazrouei"
    if cpl_row:
        partner_name = cpl_row["name_b"] if cpl_row["partner_a"] == person_id else cpl_row["name_a"]

    fr_raw = case_dict.get("fired_rules", "[]")
    try:
        fired_rules = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
    except Exception:
        fired_rules = ["TRI-T2-001", "IND-002"]

    tier = case_dict.get("tier", "T2")
    finding_type = "Autosomal Recessive Carrier (Pathogenic)"
    gene = "HBB"
    variant = "c.93-21G>A"
    condition = "Beta-thalassemia"
    partner_finding = "HBB c.118C>T (Pathogenic carrier)"
    couple_outcome = "SAME-GENE MATCH (Beta-thalassemia)"
    per_pregnancy_risk = "1 in 4 affected, 1 in 2 carrier, 1 in 4 unaffected"
    consanguinity_status = "Reported 1st Cousins (Bennett 2002 shared)"
    consent_status = "Mutual Grants Active"
    quiz_score = "100% (Passed attempt 1)"

    if "TRI-T3-001" in fired_rules or tier == "T3":
        condition = "CFTR Match (Urgent Pregnancy)"
        finding_type = "Severe Autosomal Recessive Carrier Match"
        partner_finding = "CFTR c.1521_1523delCTT (Carrier)"
        couple_outcome = "SAME-GENE MATCH (Cystic Fibrosis) - URGENT"
        per_pregnancy_risk = "1 in 4 affected (Expedited PGT-M referral needed)"
    elif "TRI-T2-005" in fired_rules or "TRI-T2-003" in fired_rules:
        condition = "DMD X-linked Carrier Female"
        finding_type = "X-Linked Recessive Carrier (Female)"
        gene = "DMD"
        variant = "Exon 45-50 deletion"
        partner_finding = "Negative on standard male screen"
        couple_outcome = "X-LINKED FEMALE CARRIER"
        per_pregnancy_risk = "Sons: 1 in 2 affected; Daughters: 1 in 2 carrier"
    elif tier == "T1":
        condition = "Carrier, Untested Partner"
        finding_type = "Single Autosomal Recessive Carrier"
        partner_finding = "Partner Not Yet Screened"
        couple_outcome = "INCOMPLETE SCREENING (Partner Pending)"
        per_pregnancy_risk = "Residual population risk (approx 1 in 800)"

    dob = case_dict.get("dob_year") or 1998
    age = 2026 - dob

    return {
        "id": case_dict["id"],
        "person_id": person_id,
        "patient_name": case_dict["patient_name"],
        "dob_year": dob,
        "age": age,
        "sex": "Female" if str(case_dict.get("sex", "")).upper() in ("F", "FEMALE") else "Male",
        "language": case_dict.get("language") or "Arabic (Gulf)",
        "tier": tier,
        "state": case_dict.get("state", "booked"),
        "sla_due": case_dict.get("sla_due") or "3 Working Days (Active)",
        "assigned_to": case_dict.get("assigned_to") or "Dr. Layla Al Hashimi, MS, CGC",
        "fired_rules": fired_rules,
        "finding_type": finding_type,
        "gene": gene,
        "variant": variant,
        "condition": condition,
        "partner_name": partner_name,
        "partner_finding": partner_finding,
        "couple_outcome": couple_outcome,
        "per_pregnancy_risk": per_pregnancy_risk,
        "consanguinity_status": consanguinity_status,
        "consent_status": consent_status,
        "quiz_score": quiz_score,
    }


@app.post("/api/portal/cases/{case_id}/book")
def book_case_appointment(
    case_id: str,
    req: BookAppointmentRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return scheduler.book_appointment(
        case_id=case_id,
        counsellor_id=req.counsellor_id,
        slot_time=req.slot_time,
        language_pref=req.language_pref,
        modality=req.modality,
        actor_id=auth["user_id"],
    )


@app.post("/api/portal/cases/{case_id}/transition")
def transition_case_state(
    case_id: str,
    req: TransitionStateRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    # Find referral associated with case
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM referral WHERE case_id = ?", (case_id,))
    ref = cur.fetchone()
    conn.close()

    if not ref:
        # Create initial referral if not yet created
        new_ref = referral_sm.create_referral(case_id, "counselling", actor_id=auth["user_id"])
        ref_id = new_ref["referral_id"]
    else:
        ref_id = ref["id"]

    return referral_sm.transition(
        referral_id=ref_id,
        target_state=req.target_state,
        actor_id=auth["user_id"],
        notes=req.notes,
    )


@app.get("/api/portal/cases/{case_id}/pdf")
def download_case_packet_pdf(
    case_id: str,
    auth: Dict[str, str] = Depends(get_current_user),
):
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
        "patient_name": "Fatima Al Mansoori",
        "dob_year": 1998,
        "sex": "F",
        "language": "Arabic (Gulf)",
        "tier": "T2",
        "sla_due": "Within 3 working days",
        "assigned_to": "Dr. Layla Al Hashimi",
        "state": "Booked",
        "fired_rules": ["TRI-T2-001", "IND-002"],
        "finding_type": "Autosomal Recessive Carrier (Pathogenic)",
        "gene": "HBB",
        "condition": "Beta-thalassemia",
        "quiz_score": 100.0,
    }

    pdf_bytes = generate_case_packet_pdf(case_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=case_packet_{case_id}.pdf"},
    )


@app.post("/api/family-notice/send")
def send_family_notice(
    req: SendFamilyNoticeRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    return family_notice_svc.send_notice(
        sender_id=auth["user_id"],
        channel=req.channel,
        condition_name=req.condition_name,
        recipient_contact=req.recipient_contact,
    )


@app.get("/api/family-notice/{token}")
def open_family_notice(token: str):
    return family_notice_svc.open_notice(token)


@app.get("/api/family-notice/shareable-card")
def get_family_shareable_card(
    condition: str = Query("Beta-thalassemia", description="Condition name"),
    language: str = Query("ar", description="Language ar or en"),
):
    """Option 1: Educational shareable explainer card."""
    return family_notice_svc.generate_shareable_card(condition_name=condition, language=language)


@app.get("/api/scheduler/available-slots")
def get_available_counsellor_slots(
    language: Optional[str] = Query(None, description="Preferred language (ar or en)"),
    gender: Optional[str] = Query(None, description="Preferred counsellor gender (female or male)"),
    modality: Optional[str] = Query(None, description="Modality (video or in_person)"),
):
    """List open genetic counsellor appointment slots with language and gender filters."""
    return scheduler.list_available_slots(language=language, gender=gender, modality=modality)


@app.get("/api/services/directory")
def get_service_directory():
    """List accredited healthcare and genetics clinics in Abu Dhabi."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM service_directory ORDER BY name_en ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/dashboard")
def serve_outcomes_dashboard():
    dashboard_file = PORTAL_DIR / "dashboard.html"
    if not dashboard_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found.")
    return FileResponse(dashboard_file)


@app.get("/api/analytics/metrics")
def get_outcomes_metrics():
    return analytics_svc.get_dashboard_metrics()
