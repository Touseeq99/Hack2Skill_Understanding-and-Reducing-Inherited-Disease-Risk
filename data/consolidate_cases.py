"""One-off cleanup: merge duplicate OPEN triage cases per person (created before cases were upserted).

Keeps the highest-tier (then oldest) case, unions the fired rule IDs, moves referrals / appointments /
reminders onto it, and deletes the rest. Tiers never go down. Take a copy of the database first.

Usage:  python -m data.consolidate_cases
"""

import json

from backend.database import db

RANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
CLOSED = ("closed", "downgraded_by_counsellor")


def main() -> int:
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, person_id, tier, fired_rules, state, sla_due, created_at FROM triage_case ORDER BY created_at, rowid")
    by_person = {}
    for r in cur.fetchall():
        if r["state"] not in CLOSED:
            by_person.setdefault(r["person_id"], []).append(r)
    merged = 0
    for pid, cases in by_person.items():
        if len(cases) < 2:
            continue
        keep = sorted(cases, key=lambda c: (-RANK[c["tier"]], c["created_at"]))[0]
        rules = []
        for c in cases:
            for rule in json.loads(c["fired_rules"] or "[]"):
                if rule not in rules:
                    rules.append(rule)
        best_state = "booked" if any(c["state"] in ("booked", "attended") for c in cases) else keep["state"]
        for c in cases:
            if c["id"] == keep["id"]:
                continue
            for table in ("referral", "appointment_booking", "reminder"):
                cur.execute(f"UPDATE {table} SET case_id = ? WHERE case_id = ?", (keep["id"], c["id"]))
            cur.execute("DELETE FROM triage_case WHERE id = ?", (c["id"],))
            merged += 1
        cur.execute("UPDATE triage_case SET fired_rules = ?, state = ? WHERE id = ?", (json.dumps(rules), best_state, keep["id"]))
    conn.commit()
    conn.close()
    print(f"Merged {merged} duplicate open cases.")
    return merged


if __name__ == "__main__":
    main()
