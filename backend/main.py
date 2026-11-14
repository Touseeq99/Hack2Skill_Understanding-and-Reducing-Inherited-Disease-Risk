"""FastAPI Application entrypoint for Inherited Disease Risk Platform."""

from fastapi import FastAPI, Header, HTTPException, Query, Depends
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

APP_DIR = Path(__file__).resolve().parent.parent / "app"

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
