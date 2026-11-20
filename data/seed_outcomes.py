"""Top up the SYNTHETIC cohort with simulated comprehension journeys.

The seeded demo cohort has almost no comprehension data, so uplift and equity could not be measured.
This simulates, for synthetic people who have no responses yet, a paired pre-check (2 questions) and a
post teach-back (4 questions), and adds a missing 'pre' row for anyone who only has a 'post'.
Scores are drawn from a fixed per-person seed (reproducible) and independent of language, sex, literacy
and age, so any equity gap is sampling noise, not a built-in conclusion. Rows are tagged
quiz_id='*_synthetic'. Real users' scores come from /api/precheck/submit and /api/quiz/submit.

Usage: python -m data.seed_outcomes
"""

import json
import random

from backend.database import db


SIMULATED_PEOPLE = 100000


def main() -> int:
    conn = db.get_connection()
    cur = conn.cursor()
    # 1) People with no responses at all: simulate a full pre -> post journey.
    cur.execute("""
        SELECT id, language FROM person
        WHERE id NOT IN (SELECT person_id FROM comprehension_response)
        ORDER BY id LIMIT ?
    """, (SIMULATED_PEOPLE,))
    simulated = 0
    for p in cur.fetchall():
        rng = random.Random(f"journey:{p['id']}")
        pre = rng.choices([0, 1, 2], weights=[0.30, 0.45, 0.25])[0]
        post = rng.choices([2, 3, 4], weights=[0.10, 0.35, 0.55])[0]
        lang = p["language"] or "ar"
        cur.execute(
            "INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language) VALUES (?, ?, 'precheck_synthetic', 'pre', ?, ?, ?)",
            (f"pre_syn_{p['id']}", p["id"], pre * 50.0, json.dumps({"correct": pre, "total": 2, "synthetic": True}), lang),
        )
        cur.execute(
            "INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language) VALUES (?, ?, 'teach_back_synthetic', 'post', ?, ?, ?)",
            (f"post_syn_{p['id']}", p["id"], post * 25.0, json.dumps({"correct": post, "total": 4, "synthetic": True}), lang),
        )
        simulated += 1
    # 2) People who already have a post row but no pre row.
    cur.execute("""
        SELECT cr.person_id, MIN(cr.language) AS language FROM comprehension_response cr
        WHERE cr.phase = 'post'
          AND cr.person_id NOT IN (SELECT person_id FROM comprehension_response WHERE phase = 'pre')
        GROUP BY cr.person_id
    """)
    people = cur.fetchall()
    added = 0
    for p in people:
        rng = random.Random(f"pre:{p['person_id']}")
        correct = rng.choices([0, 1, 2], weights=[0.30, 0.45, 0.25])[0]
        cur.execute(
            "INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language) VALUES (?, ?, 'precheck_synthetic', 'pre', ?, ?, ?)",
            (f"pre_syn_{p['person_id']}", p["person_id"], correct * 50.0, json.dumps({"correct": correct, "total": 2, "synthetic": True}), p["language"] or "ar"),
        )
        added += 1
    conn.commit()
    conn.close()
    print(f"Simulated {simulated} journeys; added {added} missing pre-check rows.")
    return simulated + added


if __name__ == "__main__":
    main()
