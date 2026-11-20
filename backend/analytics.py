"""Outcomes and Equity Analytics service.

Every figure here is computed from database rows. When there is not enough data a metric is
returned as ``None`` (rendered as "no data yet") - nothing is estimated, defaulted or hard-coded.

Metrics tracked:
- Comprehension (teach-back) pre vs post, and % correctly stating "risk is not a diagnosis"
- Counselling uptake (% of T1/T2/T3 cases booked / attended / closed)
- Time to referral vs clinical SLA (from referral state timestamps)
- Family reach (cascade notices sent -> opened -> booked)
- Privacy events (blocked unauthorised reads, revocations honoured, audit chain integrity)
- Equity breakdowns by language, literacy preference, age band, and sex (gap computed from data)

EXPLICIT NON-METRIC:
Cancelled marriages or any single reproductive choice are STRICTLY NOT success metrics.
"""

import ast
import datetime
import json
import statistics
from typing import Dict, Any, Optional, List

from backend.database import Database, db
from backend.audit_log import audit_logger

EQUITY_GAP_THRESHOLD_POINTS = 10.0
SLA_HOURS = {"T3": 24.0, "T2": 72.0, "T1": 240.0}


def _pct(num: float, den: float) -> Optional[float]:
    return round(100.0 * num / den, 1) if den else None


def _parse_ts(value: Any) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


class AnalyticsService:
    """Calculates aggregated, de-identified clinical and equity outcomes."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.audit = audit_logger

    # ---- helpers -------------------------------------------------------------
    def _group_scores(self, cur, group_sql: str) -> Dict[str, Dict[str, Any]]:
        """Average post-explanation score per group, with cohort share."""
        cur.execute(f"""
            SELECT {group_sql} AS grp, AVG(cr.score) AS avg_score, COUNT(*) AS n
            FROM comprehension_response cr
            JOIN person p ON cr.person_id = p.id
            WHERE cr.phase = 'post'
            GROUP BY grp
        """)
        rows = cur.fetchall()
        total = sum(r["n"] for r in rows)
        return {
            str(r["grp"]): {
                "avg_score": round(float(r["avg_score"]), 1),
                "count": r["n"],
                "cohort_pct": _pct(r["n"], total),
            }
            for r in rows
        }

    def _comprehension(self, cur) -> Dict[str, Any]:
        cur.execute("SELECT person_id, phase, score, answers FROM comprehension_response ORDER BY created_at")
        rows = cur.fetchall()
        pre = [r["score"] for r in rows if r["phase"] == "pre"]
        post = [r["score"] for r in rows if r["phase"] == "post"]

        # Paired (same person) uplift is the honest comparison.
        first_pre: Dict[str, float] = {}
        last_post: Dict[str, float] = {}
        for r in rows:
            if r["phase"] == "pre":
                first_pre.setdefault(r["person_id"], r["score"])
            elif r["phase"] == "post":
                last_post[r["person_id"]] = r["score"]
        paired = [(first_pre[p], last_post[p]) for p in first_pre if p in last_post]
        pre_avg = round(statistics.mean(a for a, _ in paired), 1) if paired else None
        post_paired_avg = round(statistics.mean(b for _, b in paired), 1) if paired else None

        # "Risk is not a diagnosis" item (q2) from stored answers.
        correct_q2 = 0
        answered_q2 = 0
        for r in rows:
            if r["phase"] != "post":
                continue
            try:
                ans = ast.literal_eval(r["answers"]) if r["answers"] else {}
            except (ValueError, SyntaxError):
                continue
            if "q2_risk_vs_diagnosis" in ans:
                answered_q2 += 1
                correct_q2 += 1 if ans["q2_risk_vs_diagnosis"] == "a" else 0

        return {
            "post_explanation_avg_score": round(statistics.mean(post), 1) if post else None,
            "pre_explanation_baseline_score": pre_avg,
            "post_score_same_people": post_paired_avg,
            "uplift_percentage_points": round(post_paired_avg - pre_avg, 1) if paired else None,
            "paired_people": len(paired),
            "risk_vs_diagnosis_understanding_pct": _pct(correct_q2, answered_q2),
            "risk_vs_diagnosis_n": answered_q2,
            "total_completed_quizzes": len(post),
            "total_pre_checks": len(pre),
        }

    def _wellbeing(self, cur) -> Dict[str, Any]:
        """Decisional conflict (SURE) and anxiety (GAD-2) from stored responses, paired where possible."""
        out: Dict[str, Any] = {}
        for measure, first, second in (("sure", "after_explanation", "after_counselling"),
                                       ("anxiety", "before_counselling", "after_counselling")):
            cur.execute("SELECT person_id, phase, score, flag FROM measure_response WHERE measure = ? ORDER BY rowid", (measure,))
            rows = cur.fetchall()
            a = {r["person_id"]: r for r in rows if r["phase"] == first}
            b = {r["person_id"]: r for r in rows if r["phase"] == second}
            paired = [p for p in a if p in b]
            out[measure] = {
                "phase_a": first, "phase_b": second,
                "n_a": len(a), "n_b": len(b), "paired": len(paired),
                "flag_pct_a": _pct(sum(1 for r in a.values() if r["flag"]), len(a)),
                "flag_pct_b": _pct(sum(1 for r in b.values() if r["flag"]), len(b)),
                "mean_score_a": round(statistics.mean(r["score"] for r in a.values()), 2) if a else None,
                "mean_score_b": round(statistics.mean(r["score"] for r in b.values()), 2) if b else None,
                "flag_name": "decisional_conflict" if measure == "sure" else "anxiety_screen_positive",
            }
        return out

    def _time_to_referral(self, cur) -> Dict[str, Any]:
        cur.execute("""
            SELECT tc.tier, r.timestamps_per_state
            FROM referral r JOIN triage_case tc ON tc.id = r.case_id
        """)
        by_tier: Dict[str, List[float]] = {"T3": [], "T2": [], "T1": []}
        for r in cur.fetchall():
            if r["tier"] not in by_tier:
                continue
            try:
                ts = json.loads(r["timestamps_per_state"] or "{}")
            except ValueError:
                continue
            start, booked = _parse_ts(ts.get("created")), _parse_ts(ts.get("booked"))
            if start and booked and booked >= start:
                by_tier[r["tier"]].append((booked - start).total_seconds() / 3600.0)
        out = {}
        for tier, hours in by_tier.items():
            limit = SLA_HOURS[tier]
            out[tier] = {
                "n": len(hours),
                "median_hours": round(statistics.median(hours), 2) if hours else None,
                "sla_limit_hours": limit,
                "adherence_pct": _pct(sum(1 for h in hours if h <= limit), len(hours)),
            }
        return out

    def _privacy(self, cur) -> Dict[str, Any]:
        chain_valid, chain_err = self.audit.verify_chain()
        cur.execute("SELECT COUNT(*) AS n FROM audit_event WHERE action LIKE '%unauthorized%'")
        blocked = cur.fetchone()["n"]

        # Revocations honoured: replay the audit log in insertion order. After a partner revokes
        # their couple_result grant (and until they grant again), no successful couple read may occur.
        cur.execute("SELECT id, grantor FROM consent_grant WHERE scope = 'couple_result'")
        grant_owner = {r["id"]: r["grantor"] for r in cur.fetchall()}
        cur.execute("SELECT id, partner_a, partner_b FROM couple_link")
        links = {f"couple_link:{r['id']}": (r["partner_a"], r["partner_b"]) for r in cur.fetchall()}
        cur.execute(
            "SELECT action, target, grant_id FROM audit_event "
            "WHERE action IN ('grant_created', 'grant_revoked', 'read_couple_result') ORDER BY rowid"
        )
        withdrawn: set = set()
        revocations = 0
        violations = 0
        for e in cur.fetchall():
            owner = grant_owner.get(e["grant_id"]) if e["grant_id"] else None
            if e["action"] == "grant_revoked" and owner:
                withdrawn.add(owner)
                revocations += 1
            elif e["action"] == "grant_created" and owner:
                withdrawn.discard(owner)
            elif e["action"] == "read_couple_result":
                if any(p in withdrawn for p in links.get(e["target"], ())):
                    violations += 1
        return {
            "unauthorized_attempts_blocked": blocked,
            "revocations_total": revocations,
            "reads_after_revocation": violations if revocations else None,
            "revocations_honored": (violations == 0) if revocations else None,
            "revocations_honored_pct": (100.0 if violations == 0 else None) if revocations else None,
            "cryptographic_audit_chain_valid": chain_valid,
            "audit_tamper_error": chain_err,
        }

    def _equity(self, cur) -> Dict[str, Any]:
        year = datetime.datetime.now().year
        splits = {
            "by_language": self._group_scores(cur, "p.language"),
            "by_literacy_preference": self._group_scores(cur, "p.literacy_pref"),
            "by_sex": self._group_scores(cur, "p.sex"),
            "by_age_band": self._group_scores(
                cur,
                f"CASE WHEN ({year} - p.dob_year) < 18 THEN '<18 (Minor)' "
                f"WHEN ({year} - p.dob_year) BETWEEN 18 AND 29 THEN '18-29' ELSE '30+' END",
            ),
        }
        gaps = {}
        for name, groups in splits.items():
            scores = [g["avg_score"] for g in groups.values()]
            gaps[name] = round(max(scores) - min(scores), 1) if len(scores) >= 2 else None
        known = [g for g in gaps.values() if g is not None]
        max_gap = max(known) if known else None
        return {
            **splits,
            "gap_by_split_points": gaps,
            "maximum_equity_gap_points": max_gap,
            "gap_threshold_points": EQUITY_GAP_THRESHOLD_POINTS,
            "equity_parity_achieved": (max_gap <= EQUITY_GAP_THRESHOLD_POINTS) if max_gap is not None else None,
        }

    # ---- public API ----------------------------------------------------------
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Compute full outcomes dashboard metrics from stored rows only."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) AS n FROM triage_case WHERE tier IN ('T1','T2','T3')")
            eligible = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM triage_case WHERE tier IN ('T1','T2','T3') "
                "AND state IN ('booked','attended','closed')"
            )
            booked = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM triage_case WHERE tier = 'T3'")
            t3 = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM triage_case")
            all_cases = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS sent, SUM(opened) AS opened, SUM(booked) AS booked FROM family_notice")
            fn = cur.fetchone()
            sent, opened, fbooked = fn["sent"] or 0, fn["opened"] or 0, fn["booked"] or 0

            result = {
                "data_provenance": {
                    "synthetic_cohort": True,
                    "note": "All figures are computed from the synthetic demonstration cohort. Metrics show 'no data yet' when a measurement has not been collected.",
                },
                "ethical_policy": {
                    "non_directive_principle": True,
                    "explicit_excluded_metric": "Marriage cancellations or single reproductive choices are STRICTLY NOT success metrics.",
                    "rationale": "Respecting individual cultural, religious, and family autonomy in Abu Dhabi.",
                },
                "comprehension": self._comprehension(cur),
                "counselling_uptake": {
                    "t1_t2_t3_cases_total": eligible,
                    "booked_and_attended_count": booked,
                    "uptake_percentage": _pct(booked, eligible),
                },
                "time_to_referral_vs_sla": self._time_to_referral(cur),
                "family_cascade_reach": {
                    "notices_sent": sent,
                    "notices_opened": opened,
                    "relatives_screened_or_booked": fbooked,
                    "open_rate_pct": _pct(opened, sent),
                    "booked_rate_pct": _pct(fbooked, sent),
                },
                "wellbeing": self._wellbeing(cur),
                "escalation": {"t3_cases": t3, "total_cases": all_cases, "t3_escalation_rate_pct": _pct(t3, all_cases)},
                "privacy_and_security": self._privacy(cur),
                "equity_breakdowns": self._equity(cur),
            }
        finally:
            conn.close()
        return result


analytics_svc = AnalyticsService()
