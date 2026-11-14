"""Internal appointment scheduling engine for genetic counselling."""

import uuid
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from backend.database import Database, db
from backend.audit_log import audit_logger
from backend.referral_state_machine import ReferralStateMachine


class SchedulerService:
    """Manages counsellor slot bookings and appointment lifecycle."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.audit = audit_logger
        self.referral_sm = ReferralStateMachine(self.db)

    def book_appointment(
        self,
        case_id: str,
        counsellor_id: str,
        slot_time: str,
        language_pref: str = "ar",
        modality: str = "video",
        actor_id: str = "patient",
    ) -> Dict[str, Any]:
        """Book an appointment for a triage case."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        # Check case exists
        cur.execute("SELECT id, person_id, tier, state FROM triage_case WHERE id = ?", (case_id,))
        case = cur.fetchone()
        if not case:
            conn.close()
            raise HTTPException(status_code=404, detail="Triage case not found.")

        booking_id = f"book_{uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO appointment_booking (id, case_id, counsellor_id, slot_time, language_pref, modality, status)
            VALUES (?, ?, ?, ?, ?, ?, 'booked')
        """, (booking_id, case_id, counsellor_id, slot_time, language_pref, modality))

        # Update case assigned counsellor and state to 'booked'
        cur.execute("""
            UPDATE triage_case
            SET assigned_to = ?, state = 'booked'
            WHERE id = ?
        """, (counsellor_id, case_id))

        conn.commit()
        conn.close()

        # Update or create referral record
        conn2 = self.db.get_connection()
        cur2 = conn2.cursor()
        cur2.execute("SELECT id FROM referral WHERE case_id = ?", (case_id,))
        ref = cur2.fetchone()
        conn2.close()

        if ref:
            self.referral_sm.transition(ref["id"], "booked", actor_id=actor_id, notes=f"Booked slot at {slot_time}")
        else:
            new_ref = self.referral_sm.create_referral(case_id, "counselling", actor_id=actor_id)
            self.referral_sm.transition(new_ref["referral_id"], "booked", actor_id=actor_id, notes=f"Booked slot at {slot_time}")

        self.audit.record_event(
            actor=actor_id,
            action="appointment_booked",
            target=f"booking:{booking_id}",
        )

        return {
            "booking_id": booking_id,
            "case_id": case_id,
            "counsellor_id": counsellor_id,
            "slot_time": slot_time,
            "modality": modality,
            "language_pref": language_pref,
            "status": "booked",
        }

    def list_counsellor_queue(self, counsellor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List triage cases sorted by tier priority (T3 -> T2 -> T1 -> T0) and SLA due date."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        if counsellor_id:
            cur.execute("""
                SELECT tc.*, p.name as patient_name, p.dob_year, p.sex, p.language
                FROM triage_case tc
                JOIN person p ON tc.person_id = p.id
                WHERE (tc.assigned_to = ? OR tc.assigned_to IS NULL)
                AND tc.state != 'closed'
                ORDER BY
                    CASE tc.tier
                        WHEN 'T3' THEN 1
                        WHEN 'T2' THEN 2
                        WHEN 'T1' THEN 3
                        ELSE 4
                    END ASC,
                    tc.sla_due ASC
            """, (counsellor_id,))
        else:
            cur.execute("""
                SELECT tc.*, p.name as patient_name, p.dob_year, p.sex, p.language
                FROM triage_case tc
                JOIN person p ON tc.person_id = p.id
                WHERE tc.state != 'closed'
                ORDER BY
                    CASE tc.tier
                        WHEN 'T3' THEN 1
                        WHEN 'T2' THEN 2
                        WHEN 'T1' THEN 3
                        ELSE 4
                    END ASC,
                    tc.sla_due ASC
            """)
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]


scheduler = SchedulerService()
