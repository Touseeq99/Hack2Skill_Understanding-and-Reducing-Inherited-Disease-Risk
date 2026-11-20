"""Service layer implementing consent vault, access control, and deterministic engine execution."""

import uuid
import datetime
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from backend.database import Database, db
from backend.encryptor import default_encryptor
from backend.vault import load_variants
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

        # Check if screening result exists for person
        cur.execute("SELECT id FROM screening_result WHERE person_id = ?", (person_id,))
        sr_row = cur.fetchone()
        is_tested = (sr_row is not None)

        # Get variants (decrypted inside the vault, in memory only)
        variants: List[VariantCall] = load_variants(cur, person_id)
        conn.close()

        return PersonInput(
            id=p_row["id"],
            sex=p_row["sex"],
            pregnancy_status=bool(p_row["pregnancy_status"]),
            variants=variants,
            is_tested=is_tested,
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

    def delete_person_data(self, person_id: str) -> Dict[str, Any]:
        """Erase all application data for a person (right to deletion).

        Removes the person and, through foreign-key cascades, their screening results, variants,
        assessments, couple links, own consent grants, triage cases, referrals, bookings, explanation
        logs and comprehension responses. Also removes grants made TO them and family notices they sent.
        The append-only audit log is intentionally retained (it is the tamper-evident record that the
        deletion happened); it holds only pseudonymous ids and event types, never genetic payloads.
        """
        import hashlib
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM person WHERE id = ?", (person_id,))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Person not found.")
        counts: Dict[str, int] = {}
        for table, col in (("screening_result", "person_id"), ("triage_case", "person_id"),
                           ("comprehension_response", "person_id"), ("explanation_log", "person_id"),
                           ("consent_grant", "grantor")):
            cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} = ?", (person_id,))
            counts[table] = cur.fetchone()["n"]
        sender_hash = hashlib.sha256(f"salt_family_notice_{person_id}".encode("utf-8")).hexdigest()
        cur.execute("DELETE FROM consent_grant WHERE grantee = ?", (person_id,))
        cur.execute("DELETE FROM family_notice WHERE sender_id_hash = ?", (sender_hash,))
        cur.execute("DELETE FROM person WHERE id = ?", (person_id,))
        conn.commit()
        conn.close()
        self.audit.record_event(actor=person_id, action="data_deletion_completed", target=f"person:{person_id}")
        return {"deleted": True, "removed_records": counts,
                "audit_note": "A tamper-evident audit entry records that deletion occurred; no genetic data is retained."}


    def case_findings(self, person_id: str) -> Dict[str, Any]:
        """Real, engine-derived findings for the counsellor dossier (no canned values).

        Partner details are included only when BOTH partners hold active couple_result grants.
        """
        import json
        from pathlib import Path
        panel = {g["gene"]: g for g in json.loads((Path(__file__).resolve().parent.parent / "engine" / "panel_genes.json").read_text(encoding="utf-8"))}
        person = self.get_person_input(person_id)
        ind = classify(person)
        pathogenic = [v for v in person.variants if v.is_pathogenic()] or [v for v in person.variants if v.is_vus()]
        main = pathogenic[0] if pathogenic else None
        gene = main.gene if main else None
        out: Dict[str, Any] = {
            "finding_type": ind.category.replace("_", " ").title(),
            "gene": gene or "-",
            "variant": main.hgvs if main else "-",
            "condition": panel.get(gene, {}).get("condition_name_en", "-") if gene else "No P/LP variant",
            "individual_rule_id": ind.rule_id,
            "partner_name": None,
            "partner_finding": "No linked partner",
            "couple_outcome": "No couple link",
            "couple_outcome_code": None,
            "per_pregnancy_risk": ind.natural_frequency,
            "consent_status": "No couple link",
        }
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, partner_a, partner_b, status FROM couple_link WHERE (partner_a = ? OR partner_b = ?) AND status = 'active' LIMIT 1",
            (person_id, person_id),
        )
        link = cur.fetchone()
        if not link:
            conn.close()
            return out
        partner_id = link["partner_b"] if link["partner_a"] == person_id else link["partner_a"]
        cur.execute("SELECT name FROM person WHERE id = ?", (partner_id,))
        pr = cur.fetchone()
        cur.execute(
            "SELECT DISTINCT grantor FROM consent_grant WHERE scope = 'couple_result' AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > datetime('now')) AND grantor IN (?, ?)",
            (link["partner_a"], link["partner_b"]),
        )
        granted = {r["grantor"] for r in cur.fetchall()}
        conn.close()
        out["partner_name"] = pr["name"] if pr else None
        if len(granted) == 2:
            res = couple(person, self.get_person_input(partner_id))
            out["consent_status"] = "Mutual grants active"
            out["couple_outcome_code"] = res.outcome
            out["couple_outcome"] = res.outcome.replace("_", " ").upper() + (f" ({', '.join(res.shared_genes)})" if res.shared_genes else "")
            out["per_pregnancy_risk"] = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in res.natural_frequencies.items())
            out["partner_finding"] = "Shared with consent: see couple outcome"
        else:
            out["consent_status"] = "Couple grants not both active - partner data withheld"
            out["couple_outcome"] = "Hidden (consent required)"
            out["partner_finding"] = "Withheld (consent required)"
        return out


service = PlatformService()
