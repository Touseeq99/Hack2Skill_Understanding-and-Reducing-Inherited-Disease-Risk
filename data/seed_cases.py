"""Create triage cases for the synthetic cohort by running the real router on server-derived facts.

For every person with a screening result: engine category, pregnancy status, age and (only when BOTH
partners hold active grants) the couple outcome are taken from the vault, exactly like POST /api/triage/evaluate.
Persons that route to T0 get no case (self-serve). Idempotent: the router upserts per person.

Usage:  python -m data.seed_cases
"""

from backend.database import db
from backend.service import service
from backend.triage_router import router, TriageSignals


def main() -> int:
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT p.id, p.dob_year, p.pregnancy_status FROM person p JOIN screening_result sr ON sr.person_id = p.id ORDER BY p.id")
    people = cur.fetchall()
    conn.close()
    created = 0
    for p in people:
        result = service.get_individual_assessment(p["id"], current_user_id=p["id"])
        findings = service.case_findings(p["id"])
        signals = TriageSignals(
            person_id=p["id"],
            engine_category=result.category,
            couple_outcome=findings.get("couple_outcome_code"),
            is_pregnant=bool(p["pregnancy_status"]),
            age_years=(2026 - p["dob_year"]) if p["dob_year"] else 25,
        )
        # Dry-run the tier first so T0 people do not clutter the counsellor queue.
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM triage_case WHERE person_id = ? AND state NOT IN ('closed', 'downgraded_by_counsellor')", (p["id"],))
        has_case = cur.fetchone() is not None
        conn.close()
        if result.tier == "T0" and not has_case and not (result.category == "carrier"):
            continue
        d = router.evaluate(signals)
        if d.tier == "T0":
            conn = db.get_connection()
            conn.execute("DELETE FROM triage_case WHERE id = ?", (d.case_id,))
            conn.commit()
            conn.close()
        else:
            created += 1
    print(f"Routed {created} people into the counsellor queue.")
    return created


if __name__ == "__main__":
    main()
