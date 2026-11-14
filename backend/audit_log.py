"""Tamper-evident, hash-chained audit logging service.

Every sensitive read, matching, triage escalation, and consent grant transition
is cryptographically chained to the previous entry using SHA-256.
"""

import hashlib
import datetime
import uuid
from typing import Optional, Tuple, List, Dict, Any
from pydantic import BaseModel
from backend.database import Database, db


class AuditEventModel(BaseModel):
    id: str
    actor: str
    action: str
    target: str
    grant_id: Optional[str] = None
    prev_hash: str
    hash: str
    at: str


class AuditLogService:
    """Manages append-only hash-chained audit events."""

    GENESIS_HASH = "0" * 64

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db

    def _compute_hash(
        self,
        event_id: str,
        actor: str,
        action: str,
        target: str,
        grant_id: Optional[str],
        prev_hash: str,
        at: str,
    ) -> str:
        """Compute SHA-256 hash of audit event fields."""
        payload = f"{event_id}|{actor}|{action}|{target}|{grant_id or ''}|{prev_hash}|{at}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_event(
        self,
        actor: str,
        action: str,
        target: str,
        grant_id: Optional[str] = None,
        at: Optional[str] = None,
    ) -> AuditEventModel:
        """Record an append-only audit event chained to the previous event hash."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        # Fetch last event hash
        cur.execute("SELECT hash FROM audit_event ORDER BY at DESC, rowid DESC LIMIT 1")
        last_row = cur.fetchone()
        prev_hash = last_row["hash"] if last_row else self.GENESIS_HASH

        event_id = str(uuid.uuid4())
        timestamp = at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        event_hash = self._compute_hash(event_id, actor, action, target, grant_id, prev_hash, timestamp)

        cur.execute("""
            INSERT INTO audit_event (id, actor, action, target, grant_id, prev_hash, hash, at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (event_id, actor, action, target, grant_id, prev_hash, event_hash, timestamp))

        conn.commit()
        conn.close()

        return AuditEventModel(
            id=event_id,
            actor=actor,
            action=action,
            target=target,
            grant_id=grant_id,
            prev_hash=prev_hash,
            hash=event_hash,
            at=timestamp,
        )

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """Verify the integrity of the entire audit chain.
        
        Returns:
            (True, None) if completely intact.
            (False, error_message) if tampering or broken link is detected.
        """
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, actor, action, target, grant_id, prev_hash, hash, at FROM audit_event ORDER BY at ASC, rowid ASC")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return True, None

        expected_prev = self.GENESIS_HASH
        for idx, row in enumerate(rows):
            # 1. Verify previous hash pointer
            if row["prev_hash"] != expected_prev:
                return False, f"Broken chain at index {idx} (event {row['id']}): prev_hash {row['prev_hash']} != expected {expected_prev}"

            # 2. Re-compute hash of this row
            recomputed = self._compute_hash(
                row["id"],
                row["actor"],
                row["action"],
                row["target"],
                row["grant_id"],
                row["prev_hash"],
                row["at"],
            )
            if recomputed != row["hash"]:
                return False, f"Tampered record at index {idx} (event {row['id']}): recomputed {recomputed} != stored {row['hash']}"

            expected_prev = row["hash"]

        return True, None

    def get_user_access_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve audit events related to user (where user was actor or target)."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, actor, action, target, grant_id, prev_hash, hash, at
            FROM audit_event
            WHERE actor = ? OR target LIKE ?
            ORDER BY at DESC, rowid DESC
            LIMIT ?
        """, (user_id, f"%{user_id}%", limit))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]


# Global singleton instance
audit_logger = AuditLogService()
