"""Service layer implementing consent vault, access control, and deterministic engine execution."""

import uuid
import datetime
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from backend.database import Database, db
from backend.encryptor import default_encryptor
from backend.audit_log import audit_logger
from engine.models import VariantCall, PersonInput, PersonResult, CoupleResult
from engine.risk_engine import classify, couple


class PlatformService:
    """Core platform service orchestrating database, vault encryption, audit log, and risk engine."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.encryptor = default_encryptor
        self.audit = audit_logger

    def get_person(self, person_id: str) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM person WHERE id = ?", (person_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_person_input(self, person_id: str) -> PersonInput:
        """Fetch person and decrypt variant calls to build PersonInput for pure engine."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, sex, pregnancy_status FROM person WHERE id = ?", (person_id,))
        p_row = cur.fetchone()
        if not p_row:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")

        # Get variants
        cur.execute("""
            SELECT vc.id, vc.gene, vc.hgvs, vc.zygosity, vc.classification, vc.inheritance, vc.encrypted_payload
            FROM variant_call vc
            JOIN screening_result sr ON vc.result_id = sr.id
            WHERE sr.person_id = ?
        """, (person_id,))
        v_rows = cur.fetchall()
        conn.close()

        variants: List[VariantCall] = []
        for r in v_rows:
            # Note: encrypted_payload is decrypted inside vault memory only
            variants.append(VariantCall(
                gene=r["gene"],
                hgvs=r["hgvs"],
                zygosity=r["zygosity"],
                classification=r["classification"],
                inheritance=r["inheritance"],
            ))

        return PersonInput(
            id=p_row["id"],
            sex=p_row["sex"],
            pregnancy_status=bool(p_row["pregnancy_status"]),
            variants=variants,
            is_tested=True,
        )

    def get_individual_assessment(self, person_id: str, current_user_id: str, role: str = "patient") -> PersonResult:
        """Retrieve individual risk classification with RLS policy enforcement and audit logging."""
        if not self.db.can_read_person(person_id, current_user_id, role):
            self.audit.record_event(
                actor=current_user_id,
                action="unauthorized_read_attempt",
                target=f"person:{person_id}",
            )
            raise HTTPException(status_code=403, detail="Access denied: You can only view your own genetic screening result.")

        person_input = self.get_person_input(person_id)
        result = classify(person_input)

        # Record tamper-evident audit read
        self.audit.record_event(
            actor=current_user_id,
            action="read_individual_result",
            target=f"person:{person_id}",
        )

        return result

    def create_couple_link(self, partner_a: str, partner_b: str, current_user_id: str) -> Dict[str, Any]:
        """Create a new couple link invitation."""
        if current_user_id != partner_a and current_user_id != partner_b:
            raise HTTPException(status_code=403, detail="You can only link your own account to a partner.")

        if partner_a == partner_b:
            raise HTTPException(status_code=400, detail="Partner A and Partner B must be distinct individuals.")

        link_id = f"cpl_{uuid.uuid4().hex[:12]}"
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO couple_link (id, partner_a, partner_b, status)
            VALUES (?, ?, ?, 'pending')
        """, (link_id, partner_a, partner_b))
        conn.commit()
        conn.close()

        self.audit.record_event(
            actor=current_user_id,
            action="couple_link_created",
            target=f"couple_link:{link_id}",
        )

        return {"couple_link_id": link_id, "partner_a": partner_a, "partner_b": partner_b, "status": "pending"}

    def grant_consent(
        self,
        grantor: str,
        grantee: str,
        scope: str,
        purpose: str,
        current_user_id: str,
        couple_link_id: Optional[str] = None,
        expires_days: int = 365,
    ) -> Dict[str, Any]:
        """Issue an explicit, revocable consent grant."""
        if grantor != current_user_id:
            raise HTTPException(status_code=403, detail="You can only grant consent on your own behalf.")

        grant_id = f"grant_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = (now + datetime.timedelta(days=expires_days)).isoformat()

        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO consent_grant (id, grantor, grantee, scope, purpose, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (grant_id, grantor, grantee, scope, purpose, expires_at))

        # If this is for a couple_result, check if other partner already granted, and if so activate couple_link
        if scope == "couple_result" and couple_link_id:
            cur.execute("""
                SELECT partner_a, partner_b FROM couple_link WHERE id = ?
            """, (couple_link_id,))
            link = cur.fetchone()
            if link:
                other_partner = link["partner_b"] if grantor == link["partner_a"] else link["partner_a"]
                cur.execute("""
                    SELECT id FROM consent_grant
                    WHERE grantor = ? AND scope = 'couple_result' AND revoked_at IS NULL
                """, (other_partner,))
                other_grant = cur.fetchone()
                if other_grant:
                    cur.execute("UPDATE couple_link SET status = 'active' WHERE id = ?", (couple_link_id,))

        conn.commit()
        conn.close()

        self.audit.record_event(
            actor=current_user_id,
            action="grant_created",
            target=f"grant:{grant_id}",
            grant_id=grant_id,
        )

        return {
            "grant_id": grant_id,
            "grantor": grantor,
            "grantee": grantee,
            "scope": scope,
            "purpose": purpose,
            "expires_at": expires_at,
            "status": "active",
        }

    def revoke_consent(self, grant_id: str, current_user_id: str) -> Dict[str, Any]:
        """Revoke a consent grant immediately, instantly hiding derived couple results."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT grantor, scope FROM consent_grant WHERE id = ?", (grant_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Consent grant not found.")

        if row["grantor"] != current_user_id:
            conn.close()
            raise HTTPException(status_code=403, detail="You can only revoke your own consent grants.")

        revoked_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur.execute("UPDATE consent_grant SET revoked_at = ? WHERE id = ?", (revoked_time, grant_id))
        conn.commit()
        conn.close()

        self.audit.record_event(
            actor=current_user_id,
            action="grant_revoked",
            target=f"grant:{grant_id}",
            grant_id=grant_id,
        )

        return {"grant_id": grant_id, "status": "revoked", "revoked_at": revoked_time}

    def get_couple_assessment(
        self,
        couple_link_id: str,
        current_user_id: str,
        is_consanguineous: bool = False,
        role: str = "patient",
    ) -> CoupleResult:
        """Compute or retrieve couple risk assessment with strict mutual consent check."""
        # 1. Row-Level Security Check: Both grants must be active!
        can_read = self.db.can_read_couple_result(couple_link_id, current_user_id, role)
        if not can_read:
            self.audit.record_event(
                actor=current_user_id,
                action="unauthorized_couple_read_attempt",
                target=f"couple_link:{couple_link_id}",
            )
            raise HTTPException(
                status_code=403,
                detail="Mutual consent required. The couple result is completely private and hidden unless BOTH partners have active, unrevoked consent grants."
            )

        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT partner_a, partner_b FROM couple_link WHERE id = ?", (couple_link_id,))
        link = cur.fetchone()
        conn.close()
        if not link:
            raise HTTPException(status_code=404, detail="Couple link not found.")

        p_a = self.get_person_input(link["partner_a"])
        p_b = self.get_person_input(link["partner_b"])

        # Execute pure deterministic engine
        result = couple(p_a, p_b, is_consanguineous=is_consanguineous)

        # Audit log read
        self.audit.record_event(
            actor=current_user_id,
            action="read_couple_result",
            target=f"couple_link:{couple_link_id}",
        )

        return result


service = PlatformService()
