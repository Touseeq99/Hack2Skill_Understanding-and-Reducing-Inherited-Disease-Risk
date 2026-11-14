"""FastAPI Application entrypoint for Inherited Disease Risk Platform."""

from fastapi import FastAPI, Header, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

from backend.database import db
from backend.service import service
from backend.audit_log import audit_logger
from engine.models import PersonResult, CoupleResult

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


@app.get("/api/audit/events")
def list_audit_events(
    limit: int = 50,
    auth: Dict[str, str] = Depends(get_current_user),
):
    conn = db.get_connection()
    cur = conn.cursor()
    if auth["role"] == "admin":
        cur.execute("SELECT * FROM audit_event ORDER BY at DESC, rowid DESC LIMIT ?", (limit,))
    else:
        cur.execute("SELECT * FROM audit_event WHERE actor = ? ORDER BY at DESC, rowid DESC LIMIT ?", (auth["user_id"], limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
