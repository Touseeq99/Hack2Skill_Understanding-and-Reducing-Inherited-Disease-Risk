"""FastAPI Application entrypoint for Inherited Disease Risk Platform."""

from fastapi import FastAPI, Header, HTTPException, Query, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from pathlib import Path
import os

from backend.database import db
from backend.auth import current_user, require_staff, require_roles, login as auth_login, role_for
from backend.fhir_ingest import ingest_bundle
from backend.reminders import process_missed_appointments
from backend.service import service
from backend.audit_log import audit_logger
from engine.models import PersonResult, CoupleResult
from explain.graph_flow import graph, QUIZ_QUESTIONS, FlowState
from explain.pipeline import pipeline
from explain.options_library import options_for
from backend.measures import score_measure, PHASES
from backend import rag
from backend.safety import SAFETY_RESOURCES, is_out_of_hours, next_counsellor_window
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

app.mount("/assets", StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "app" / "assets")), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authentication: signed bearer tokens (see backend/auth.py). Roles come from the token, not from headers.
get_current_user = current_user


class LoginRequest(BaseModel):
    user_id: str
    otp: str


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

_HEALTH_CHAIN_CACHE = {"at": None, "result": (True, None)}


@app.on_event("startup")
def warm_up_safety_model():
    """Load the embedding model in the background so the first chat message is not slow."""
    import threading
    from backend import ml_classifier
    threading.Thread(target=ml_classifier.available, daemon=True).start()


@app.get("/health")
def health_check():
    from backend import ml_classifier
    import time as _time
    # Full chain verification is O(n); /health caches it for 30 s (staff can force a full check at /api/audit/verify).
    cached = _HEALTH_CHAIN_CACHE
    if cached["at"] is None or _time.time() - cached["at"] > 30:
        cached["result"] = audit_logger.verify_chain()
        cached["at"] = _time.time()
    valid, err = cached["result"]
    return {
        "safety_classifier": {"rules": True, "embedding_model": ml_classifier.available() if os.environ.get("SAFETY_ML", "1") != "0" else False},
        "status": "healthy",
        "engine_version": "v1",
        "clinical_signoff": "DRAFT - requires clinical sign-off",
        "audit_chain_valid": valid,
        "audit_error": err,
    }


@app.post("/api/auth/login")
def login_endpoint(req: LoginRequest):
    """Demo one-time-code login. Returns a signed bearer token; the role is decided server-side."""
    token = auth_login(req.user_id, req.otp)
    audit_logger.record_event(actor=req.user_id, action="login", target=f"user:{req.user_id}")
    return {"access_token": token, "token_type": "bearer", "user_id": req.user_id, "role": role_for(req.user_id)}


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


class DeleteAccountRequest(BaseModel):
    confirm: str


@app.post("/api/users/me/delete")
def delete_my_data(req: DeleteAccountRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Right to deletion: the caller erases their own application data (typed confirmation required)."""
    if auth["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only a patient can delete their own data.")
    if req.confirm != "DELETE":
        raise HTTPException(status_code=422, detail='Type "DELETE" to confirm.')
    audit_logger.record_event(actor=auth["user_id"], action="data_deletion_requested", target=f"person:{auth['user_id']}")
    return service.delete_person_data(auth["user_id"])


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


@app.get("/api/grants/mine")
def list_my_grants(auth: Dict[str, str] = Depends(get_current_user)):
    """The caller's own consent grants (active first), so the UI can show and revoke them."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, grantee, scope, purpose, expires_at, revoked_at FROM consent_grant WHERE grantor = ? "
        "ORDER BY (revoked_at IS NOT NULL), rowid DESC",
        (auth["user_id"],),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/my/couple-link")
def get_my_couple_link(auth: Dict[str, str] = Depends(get_current_user)):
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, partner_a, partner_b, status FROM couple_link WHERE (partner_a = ? OR partner_b = ?) AND status = 'active' LIMIT 1",
        (auth["user_id"], auth["user_id"]),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No active couple link.")
    partner = row["partner_b"] if row["partner_a"] == auth["user_id"] else row["partner_a"]
    return {"id": row["id"], "partner_id": partner}


@app.get("/api/my/case")
def get_my_open_case(auth: Dict[str, str] = Depends(get_current_user)):
    """The caller's current open triage case (used to book counselling)."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tier, state, sla_due FROM triage_case WHERE person_id = ? AND state NOT IN ('closed', 'downgraded_by_counsellor') "
        "ORDER BY CASE tier WHEN 'T3' THEN 1 WHEN 'T2' THEN 2 WHEN 'T1' THEN 3 ELSE 4 END, created_at DESC LIMIT 1",
        (auth["user_id"],),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No open case.")
    return dict(row)


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
def verify_audit_log(auth: Dict[str, str] = Depends(get_current_user)):
    require_staff(auth)
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


class MeasureRequest(BaseModel):
    measure: str
    phase: str
    items: list


@app.post("/api/measures")
def submit_measure(req: MeasureRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Store a SURE (decisional conflict) or anxiety (GAD-2) response; the score is computed here."""
    import json as _json
    import uuid as _uuid
    if req.measure not in PHASES or req.phase not in PHASES[req.measure]:
        raise HTTPException(status_code=422, detail="Unknown measure or phase.")
    try:
        items = [int(i) for i in req.items]
        scored = score_measure(req.measure, items)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO measure_response (id, person_id, measure, phase, score, flag, items) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"mr_{_uuid.uuid4().hex[:12]}", auth["user_id"], req.measure, req.phase, scored["score"], 1 if scored["flag"] else 0, _json.dumps(items)),
    )
    conn.commit()
    conn.close()
    audit_logger.record_event(actor=auth["user_id"], action=f"measure_{req.measure}_{req.phase}", target=f"person:{auth['user_id']}")
    return {"stored": True, "score": scored["score"], "flag": scored["flag"], "flag_name": scored["flag_name"]}


@app.get("/api/options")
def get_options(language: str = Query("ar"), auth: Dict[str, str] = Depends(get_current_user)):
    """Neutral options library; detailed options for T2/T3 are released after counselling."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT tier, state FROM triage_case WHERE person_id = ? AND state NOT IN ('downgraded_by_counsellor') "
        "ORDER BY CASE tier WHEN 'T3' THEN 1 WHEN 'T2' THEN 2 WHEN 'T1' THEN 3 ELSE 4 END, created_at DESC LIMIT 1",
        (auth["user_id"],),
    )
    row = cur.fetchone()
    conn.close()
    tier, state = (row["tier"], row["state"]) if row else ("T0", "created")
    return {"tier": tier, "case_state": state, "options": options_for(language, tier, state)}


class ValuesRequest(BaseModel):
    answers: Dict[str, str]
    share_with_counsellor: bool = False


@app.post("/api/values")
def save_values(req: ValuesRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Store the values-clarification answers. They reach the counsellor only if the user opts in."""
    import json as _json
    import uuid as _uuid
    if len(req.answers) > 10 or any(len(k) > 40 or len(v) > 80 for k, v in req.answers.items()):
        raise HTTPException(status_code=422, detail="Invalid answers.")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM values_response WHERE person_id = ?", (auth["user_id"],))
    cur.execute(
        "INSERT INTO values_response (id, person_id, answers, share_with_counsellor) VALUES (?, ?, ?, ?)",
        (f"val_{_uuid.uuid4().hex[:12]}", auth["user_id"], _json.dumps(req.answers), 1 if req.share_with_counsellor else 0),
    )
    conn.commit()
    conn.close()
    audit_logger.record_event(
        actor=auth["user_id"],
        action="values_shared_with_counsellor" if req.share_with_counsellor else "values_saved_private",
        target=f"person:{auth['user_id']}",
    )
    return {"saved": True, "shared_with_counsellor": req.share_with_counsellor}


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


class PrecheckRequest(BaseModel):
    correct: int = Field(ge=0)
    total: int = Field(gt=0)
    feeling: Optional[str] = None
    language: str = "ar"


@app.post("/api/precheck/submit")
def submit_precheck(req: PrecheckRequest, auth: Dict[str, str] = Depends(get_current_user)):
    """Store the pre-result knowledge check (baseline for measuring comprehension uplift)."""
    import json as _json
    import uuid as _uuid
    if req.correct > req.total:
        raise HTTPException(status_code=422, detail="correct cannot exceed total")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language) VALUES (?, ?, ?, 'pre', ?, ?, ?)",
        (f"pre_{_uuid.uuid4().hex[:12]}", auth["user_id"], "precheck_v1", round(100.0 * req.correct / req.total, 1),
         _json.dumps({"correct": req.correct, "total": req.total, "feeling": req.feeling}), req.language),
    )
    conn.commit()
    conn.close()
    audit_logger.record_event(actor=auth["user_id"], action="precheck_submitted", target=f"person:{auth['user_id']}")
    return {"stored": True, "score": round(100.0 * req.correct / req.total, 1)}


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


def build_server_signals(auth: Dict[str, str], **client_signals) -> TriageSignals:
    """Engine category, pregnancy status, age, couple outcome and anxiety screen come from the vault;
    the client can only add behavioural / self-reported signals (which can only raise a tier)."""
    user_id = auth["user_id"]
    person = service.get_person(user_id)
    if not person:
        raise HTTPException(status_code=404, detail="User profile not found.")
    result = service.get_individual_assessment(user_id, current_user_id=user_id, role=auth["role"])
    couple_outcome = service.case_findings(user_id).get("couple_outcome_code")
    dob = person.get("dob_year")
    mconn = db.get_connection()
    mcur = mconn.cursor()
    mcur.execute("SELECT flag FROM measure_response WHERE person_id = ? AND measure = 'anxiety' ORDER BY rowid DESC LIMIT 1", (user_id,))
    arow = mcur.fetchone()
    mconn.close()
    return TriageSignals(
        person_id=user_id,
        engine_category=result.category,
        couple_outcome=couple_outcome,
        is_pregnant=bool(person.get("pregnancy_status")),
        age_years=(2026 - dob) if dob else 25,
        anxiety_screen_positive=bool(arow and arow["flag"]),
        **client_signals,
    )


@app.post("/api/triage/evaluate")
def evaluate_triage(
    req: TriageEvaluateRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Route the caller (see build_server_signals for which facts the server derives itself)."""
    signals = build_server_signals(
        auth,
        teach_back_failed_twice=req.teach_back_failed_twice,
        user_message=req.user_message,
        reopen_count_48h=req.reopen_count_48h,
        symptoms_reported=req.symptoms_reported,
        distress_signal=req.distress_signal,
    )
    return router.evaluate(signals)


@app.get("/api/safety-resources")
def get_safety_resources():
    """Emergency and crisis contacts (public, no login needed)."""
    return {**SAFETY_RESOURCES, "out_of_hours": is_out_of_hours(), "next_counsellor_window": next_counsellor_window()}


@app.post("/api/chat/ask")
def ask_chat_assistant(
    req: ChatAskRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Classify the message, store it for the counsellor, and ROUTE: risk signals raise a case tier.
    The assistant never answers 'what should we do'; it returns a fixed handoff and books a human."""
    import json as _json
    import uuid as _uuid
    if len(req.query) > 1000:
        raise HTTPException(status_code=422, detail="Message too long.")
    res = intent_classifier.classify_intent(req.query, req.language)
    recognised = bool(res["detected_intents"])

    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_message (id, person_id, text, intents) VALUES (?, ?, ?, ?)",
        (f"chat_{_uuid.uuid4().hex[:12]}", auth["user_id"], req.query, _json.dumps(res["detected_intents"])),
    )
    conn.commit()
    conn.close()
    # The append-only audit log records the event and intent labels only, never the message text.
    audit_logger.record_event(
        actor=auth["user_id"], action="chat_intent_query",
        target=f"person:{auth['user_id']} intents={','.join(res['detected_intents']) or 'none'}",
    )

    triage = None
    if auth["role"] == "patient" and service.get_person(auth["user_id"]):
        decision = router.evaluate(build_server_signals(auth, user_message=req.query))
        triage = {"tier": decision.tier, "fired_rules": decision.fired_rules, "fired_rules_now": decision.fired_rules_now, "case_id": decision.case_id,
                  "sla_due": decision.sla_due, "system_action": decision.system_action}
    # Education answers come ONLY from the approved FAQ library, and only when nothing needs a human first.
    needs_human_first = any(i in res["detected_intents"] for i in ("distress", "coercion", "decision_question"))
    faq_answer = None if needs_human_first else rag.answer(req.query, req.language or "en")
    urgent = res["is_distress"] or res["is_coercion"]  # based on THIS message, not on a sticky case tier
    return {
        **res,
        "recognised": recognised,
        "answer": faq_answer,
        "triage": triage,
        "safety": ({**SAFETY_RESOURCES, "out_of_hours": is_out_of_hours(), "next_counsellor_window": next_counsellor_window()} if urgent else None),
        # Keyword recall is limited (see docs): an unrecognised message is never treated as 'safe'.
        "human_offer": True,
    }


@app.post("/api/fhir/import")
def import_fhir_result(bundle: Dict[str, Any], auth: Dict[str, str] = Depends(get_current_user)):
    """Lab-to-vault ingestion of a FHIR DiagnosticReport bundle. Only lab or admin accounts may call it."""
    require_roles(auth, "lab", "admin")
    return ingest_bundle(db, audit_logger, bundle, actor=auth["user_id"])


@app.post("/api/admin/run-reminders")
def run_reminder_sweep(auth: Dict[str, str] = Depends(get_current_user)):
    require_staff(auth)
    return process_missed_appointments(db, audit_logger)


@app.get("/api/portal/outreach")
def list_outreach_tasks(auth: Dict[str, str] = Depends(get_current_user)):
    """Counsellor outreach tasks created after a missed appointment on a T2/T3 case."""
    require_staff(auth)
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.case_id, r.message, r.created_at, tc.tier FROM reminder r JOIN triage_case tc ON tc.id = r.case_id "
        "WHERE r.kind = 'counsellor_outreach' AND r.resolved = 0 ORDER BY tc.tier DESC, r.created_at"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/my/reminders")
def my_reminders(auth: Dict[str, str] = Depends(get_current_user)):
    """The caller's content-free appointment reminders."""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.message, r.created_at FROM reminder r JOIN triage_case tc ON tc.id = r.case_id "
        "WHERE tc.person_id = ? AND r.kind = 'gentle_reminder' ORDER BY r.created_at DESC LIMIT 5", (auth["user_id"],))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/portal/queue")
def list_counsellor_queue(
    auth: Dict[str, str] = Depends(get_current_user),
):
    """Retrieve active triage queue decorated with live patient and condition data."""
    require_staff(auth)
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
        sla_text = {"T3": "Urgent: 24h SLA", "T2": "Priority: 3 Days SLA", "T1": "Routine: 10 Days SLA"}.get(tier, "Self-serve")
        try:
            cond = service.case_findings(it["person_id"])["condition"]
        except Exception:
            cond = "Unavailable"

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
    require_staff(auth)
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
        raise HTTPException(status_code=404, detail="Case not found.")

    case_dict = dict(row)
    person_id = case_dict["person_id"]

    conn.close()
    try:
        fired_rules = json.loads(case_dict["fired_rules"]) if isinstance(case_dict.get("fired_rules"), str) else (case_dict.get("fired_rules") or [])
    except Exception:
        fired_rules = []

    findings = service.case_findings(person_id)
    cur_conn = db.get_connection()
    qcur = cur_conn.cursor()
    qcur.execute("SELECT AVG(score) AS s, COUNT(*) AS n FROM comprehension_response WHERE person_id = ?", (person_id,))
    qrow = qcur.fetchone()
    cur_conn.close()
    quiz_score = f"{round(qrow['s'])}% ({qrow['n']} attempt(s))" if qrow and qrow["n"] else "No teach-back recorded yet"

    vconn = db.get_connection()
    vcur = vconn.cursor()
    vcur.execute("SELECT answers FROM values_response WHERE person_id = ? AND share_with_counsellor = 1", (person_id,))
    vrow = vcur.fetchone()
    vconn.close()
    shared_values = json.loads(vrow["answers"]) if vrow else None

    ecur = db.get_connection()
    c2 = ecur.cursor()
    c2.execute("SELECT DISTINCT template_ids FROM explanation_log WHERE person_id = ?", (person_id,))
    _ids = set()
    for r in c2.fetchall():
        try:
            parsed = json.loads(r["template_ids"]) if isinstance(r["template_ids"], str) else r["template_ids"]
        except ValueError:
            parsed = [r["template_ids"]]
        _ids.update(parsed if isinstance(parsed, list) else [parsed])
    explanations = sorted(i for i in _ids if i)
    c2.execute("SELECT text FROM chat_message WHERE person_id = ? ORDER BY rowid DESC LIMIT 5", (person_id,))
    questions = [r["text"] for r in c2.fetchall()]
    ecur.close()

    dob = case_dict.get("dob_year")
    age = (2026 - dob) if dob else None
    sex = str(case_dict.get("sex") or "").upper()

    return {
        "id": case_dict["id"],
        "person_id": person_id,
        "patient_name": case_dict["patient_name"],
        "dob_year": dob,
        "age": age,
        "sex": "Female" if sex in ("F", "FEMALE") else ("Male" if sex in ("M", "MALE") else "Not recorded"),
        "language": case_dict.get("language") or "Not recorded",
        "tier": case_dict.get("tier"),
        "state": case_dict.get("state"),
        "sla_due": case_dict.get("sla_due"),
        "assigned_to": case_dict.get("assigned_to") or "Unassigned",
        "fired_rules": fired_rules,
        "consanguinity_status": "Not recorded",
        "quiz_score": quiz_score,
        "shared_values": shared_values,
        "explanations_reviewed": explanations,
        "questions_asked": questions,
        **findings,
    }


@app.post("/api/portal/cases/{case_id}/book")
def book_case_appointment(
    case_id: str,
    req: BookAppointmentRequest,
    auth: Dict[str, str] = Depends(get_current_user),
):
    if not db.can_read_triage_case(case_id, auth["user_id"], auth["role"]):
        raise HTTPException(status_code=403, detail="You can only book counselling for your own case.")
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
    require_staff(auth)
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
    require_staff(auth)
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

    if not row:
        raise HTTPException(status_code=404, detail="Case not found.")
    case_data = dict(row)
    case_data["case_id"] = case_id
    case_data.update(service.case_findings(case_data["person_id"]))
    import json as _json
    try:
        case_data["fired_rules"] = _json.loads(case_data["fired_rules"]) if isinstance(case_data.get("fired_rules"), str) else list(case_data.get("fired_rules") or [])
    except Exception:
        case_data["fired_rules"] = []
    for k, default in (("assigned_to", "Unassigned"), ("language", "Not recorded"), ("sla_due", "-"), ("sex", "-")):
        case_data[k] = case_data.get(k) or default

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


@app.get("/api/family-notice/shareable-card")
def get_family_shareable_card(
    condition: str = Query("Beta-thalassemia", description="Condition name"),
    language: str = Query("ar", description="Language ar or en"),
):
    """Option 1: Educational shareable explainer card."""
    return family_notice_svc.generate_shareable_card(condition_name=condition, language=language)


@app.get("/api/family-notice/{token}")
def open_family_notice(token: str):
    return family_notice_svc.open_notice(token)


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
def get_outcomes_metrics(auth: Dict[str, str] = Depends(get_current_user)):
    require_staff(auth)
    return analytics_svc.get_dashboard_metrics()
