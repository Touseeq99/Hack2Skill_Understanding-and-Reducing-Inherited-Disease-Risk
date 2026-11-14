"""Referral and Counsellor Case State Machine.

Lifecycle transitions:
created -> offered -> booked -> attended ->
  (confirmatory_ordered -> confirmatory_resulted) ->
  (specialist_referred -> specialist_seen) -> closed
"""

import datetime
import json
import uuid
from typing import Dict, Any, Optional
from fastapi import HTTPException
from backend.database import Database, db
from backend.audit_log import audit_logger


ALLOWED_TRANSITIONS = {
    "created": ["offered", "booked", "closed"],
    "offered": ["booked", "closed"],
    "booked": ["attended", "offered", "closed"],
    "attended": ["confirmatory_ordered", "specialist_referred", "closed"],
    "confirmatory_ordered": ["confirmatory_resulted", "closed"],
    "confirmatory_resulted": ["specialist_referred", "closed"],
    "specialist_referred": ["specialist_seen", "closed"],
    "specialist_seen": ["closed"],
    "closed": [],  # Terminal state
}


class ReferralStateMachine:
    """Manages clinical referral state transitions and tracking."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.audit = audit_logger

    def transition(
        self,
        referral_id: str,
        target_state: str,
        actor_id: str,
        role: str = "counsellor",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transition a referral case to a new state if allowed by state machine."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, case_id, service_id, state, timestamps_per_state, notes FROM referral WHERE id = ?", (referral_id,))
        ref = cur.fetchone()
        if not ref:
            conn.close()
            raise HTTPException(status_code=404, detail="Referral record not found.")

        current_state = ref["state"]
        allowed = ALLOWED_TRANSITIONS.get(current_state, [])
        if target_state not in allowed:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid state transition from '{current_state}' to '{target_state}'. Allowed: {allowed}"
            )

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            timestamps = json.loads(ref["timestamps_per_state"]) if ref["timestamps_per_state"] else {}
        except Exception:
            timestamps = {}
        timestamps[target_state] = now_str

        combined_notes = (ref["notes"] or "") + (f"\n[{now_str}] {notes}" if notes else "")

        cur.execute("""
            UPDATE referral
            SET state = ?, timestamps_per_state = ?, notes = ?
            WHERE id = ?
        """, (target_state, json.dumps(timestamps), combined_notes.strip(), referral_id))

        # If referral is closed or attended, update parent triage_case as well
        if target_state == "closed":
            cur.execute("UPDATE triage_case SET state = 'closed' WHERE id = ?", (ref["case_id"],))

        conn.commit()
        conn.close()

        # Audit log the state transition
        self.audit.record_event(
            actor=actor_id,
            action=f"referral_state_{target_state}",
            target=f"referral:{referral_id}",
        )

        return {
            "referral_id": referral_id,
            "case_id": ref["case_id"],
            "previous_state": current_state,
            "current_state": target_state,
            "timestamps": timestamps,
        }

    def create_referral(
        self,
        case_id: str,
        service_id: str,
        actor_id: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new referral attached to a triage case."""
        ref_id = f"ref_{uuid.uuid4().hex[:12]}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        timestamps = {"created": now_str}

        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO referral (id, case_id, service_id, state, timestamps_per_state, notes)
            VALUES (?, ?, ?, 'created', ?, ?)
        """, (ref_id, case_id, service_id, json.dumps(timestamps), notes or "Initial referral created"))
        conn.commit()
        conn.close()

        self.audit.record_event(
            actor=actor_id,
            action="referral_created",
            target=f"referral:{ref_id}",
        )

        return {
            "referral_id": ref_id,
            "case_id": case_id,
            "service_id": service_id,
            "state": "created",
            "created_at": now_str,
        }


referral_sm = ReferralStateMachine()
