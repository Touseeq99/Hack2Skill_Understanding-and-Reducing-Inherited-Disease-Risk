"""Missed-appointment follow-up (PDF section 7): gentle reminder first, then counsellor outreach for T2/T3.

Sweep logic (idempotent; run from POST /api/admin/run-reminders or a scheduler):
1. A 'booked' appointment whose slot ended more than GRACE_HOURS ago is marked 'no_show' and the patient gets a
   content-free, gentle reminder (no result details, no gene names).
2. For T2/T3 cases still not attended or rebooked OUTREACH_AFTER_HOURS after the reminder, a counsellor outreach
   task is created for the assigned counsellor (or the queue). T1 cases receive only the reminder.
"""

import datetime
import uuid
from typing import Any, Dict, Optional

GRACE_HOURS = 1
OUTREACH_AFTER_HOURS = 48

REMINDER_TEXT_EN = "You have a message about your appointment. You can rebook any time, or talk to a person."
REMINDER_TEXT_AR = "لديكِ رسالة بخصوص موعدك. يمكنك إعادة الحجز في أي وقت أو التحدث مع مختص."


def _parse(ts: str) -> Optional[datetime.datetime]:
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def process_missed_appointments(db, audit, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT ab.id, ab.case_id, ab.slot_time, tc.tier, tc.assigned_to
        FROM appointment_booking ab JOIN triage_case tc ON tc.id = ab.case_id
        WHERE ab.status = 'booked'
    """)
    reminders = 0
    for ab in cur.fetchall():
        slot = _parse(ab["slot_time"])
        if slot and now - slot > datetime.timedelta(hours=GRACE_HOURS):
            cur.execute("UPDATE appointment_booking SET status = 'no_show' WHERE id = ?", (ab["id"],))
            cur.execute(
                "INSERT INTO reminder (id, case_id, kind, message, created_at) VALUES (?, ?, 'gentle_reminder', ?, ?)",
                (f"rem_{uuid.uuid4().hex[:12]}", ab["case_id"], REMINDER_TEXT_EN, now.isoformat()),
            )
            reminders += 1

    outreach = 0
    cur.execute("""
        SELECT r.case_id, r.created_at, tc.tier, tc.state, tc.assigned_to
        FROM reminder r JOIN triage_case tc ON tc.id = r.case_id
        WHERE r.kind = 'gentle_reminder'
          AND tc.tier IN ('T2', 'T3')
          AND tc.state NOT IN ('attended', 'closed', 'downgraded_by_counsellor')
          AND NOT EXISTS (SELECT 1 FROM reminder o WHERE o.case_id = r.case_id AND o.kind = 'counsellor_outreach')
          AND NOT EXISTS (SELECT 1 FROM appointment_booking b WHERE b.case_id = r.case_id AND b.status = 'booked')
    """)
    for r in cur.fetchall():
        created = _parse(r["created_at"])
        if created and now - created >= datetime.timedelta(hours=OUTREACH_AFTER_HOURS):
            cur.execute(
                "INSERT INTO reminder (id, case_id, kind, message, created_at) VALUES (?, ?, 'counsellor_outreach', ?, ?)",
                (f"rem_{uuid.uuid4().hex[:12]}", r["case_id"], f"Missed appointment ({r['tier']}): counsellor to contact the patient.", now.isoformat()),
            )
            outreach += 1
    conn.commit()
    conn.close()
    if reminders or outreach:
        audit.record_event(actor="system:reminders", action="reminder_sweep", target=f"reminders={reminders};outreach={outreach}")
    return {"gentle_reminders_created": reminders, "counsellor_outreach_created": outreach}
