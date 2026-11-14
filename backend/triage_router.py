"""Triage Router engine implementing T0-T3 escalation rules.

Core rules:
- Final tier = max(highest rule triggered, existing case tier).
- Rules can ONLY raise a tier, never lower it automatically.
- Every decision stores fired rule IDs and logs an audit event.
"""

import datetime
import uuid
from typing import List, Optional
from pydantic import BaseModel
from backend.database import Database, db
from backend.audit_log import audit_logger
from backend.intent_classifier import intent_classifier


TIER_RANKS = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
RANK_TO_TIER = {0: "T0", 1: "T1", 2: "T2", 3: "T3"}


def max_tier(t1: str, t2: Optional[str]) -> str:
    """Return the higher of two tiers (tiers only escalate)."""
    if not t2:
        return t1
    r1 = TIER_RANKS.get(t1, 0)
    r2 = TIER_RANKS.get(t2, 0)
    return RANK_TO_TIER[max(r1, r2)]


def compute_sla_due(tier: str, base_time: Optional[datetime.datetime] = None) -> Optional[str]:
    """Calculate SLA due timestamp based on tier policy."""
    now = base_time or datetime.datetime.now(datetime.timezone.utc)
    if tier == "T3":
        # Same day / 24 hours
        return (now + datetime.timedelta(hours=24)).isoformat()
    elif tier == "T2":
        # 3 working days
        return (now + datetime.timedelta(days=3)).isoformat()
    elif tier == "T1":
        # 10 working days
        return (now + datetime.timedelta(days=10)).isoformat()
    # T0 has no urgent human SLA
    return None


class TriageSignals(BaseModel):
    """Input signals evaluated by the triage router."""
    person_id: str
    engine_category: str = "screen_negative"
    couple_outcome: Optional[str] = None
    is_pregnant: bool = False
    age_years: int = 25
    teach_back_failed_twice: bool = False
    user_message: Optional[str] = None
    reopen_count_48h: int = 0
    symptoms_reported: bool = False
    distress_signal: bool = False
    existing_case_tier: Optional[str] = None


class TriageDecision(BaseModel):
    """Result of triage routing."""
    case_id: str
    person_id: str
    tier: str
    fired_rules: List[str]
    sla_due: Optional[str]
    system_action: str
    directive_handoff_message: Optional[str] = None
    safety_resources_shown: bool = False
    state: str = "created"


class TriageRouter:
    """Evaluates triage rules and manages case lifecycle in database."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.audit = audit_logger
        self.classifier = intent_classifier

    def evaluate(self, signals: TriageSignals) -> TriageDecision:
        fired_rules: List[str] = []
        directive_handoff = None
        safety_resources = False

        # --- T3 Triggers (Highest Priority) ---
        # TRI-T3-005: Minor detected (under 18 blocks self-serve)
        if signals.age_years < 18:
            fired_rules.append("TRI-T3-005")

        # TRI-T3-001: possible_affected with pregnancy, distress, or symptoms
        if signals.engine_category == "possible_affected" and (
            signals.is_pregnant or signals.distress_signal or signals.symptoms_reported
        ):
            fired_rules.append("TRI-T3-001")

        # TRI-T3-002: couple at risk (same_gene_match) and currently pregnant
        if signals.couple_outcome == "same_gene_match" and signals.is_pregnant:
            fired_rules.append("TRI-T3-002")

        # Intent classification on user message
        if signals.user_message:
            intent_res = self.classifier.classify_intent(signals.user_message)
            if intent_res["is_distress"]:
                fired_rules.append("TRI-T3-003")
                safety_resources = True
            if intent_res["is_coercion"]:
                fired_rules.append("TRI-T3-004")
                safety_resources = True
            if intent_res["is_decision_question"]:
                fired_rules.append("TRI-T2-005")
                directive_handoff = intent_res["handoff_message"]
            elif "reproductive_options" in intent_res["detected_intents"]:
                fired_rules.append("TRI-T2-006")
            elif "help_request" in intent_res["detected_intents"]:
                fired_rules.append("TRI-T1-003")

        # --- T2 Triggers ---
        if signals.couple_outcome in ("same_gene_match", "uncertain_match", "xlinked_risk"):
            if signals.couple_outcome == "same_gene_match":
                fired_rules.append("TRI-T2-001")
            elif signals.couple_outcome == "uncertain_match":
                fired_rules.append("TRI-T2-004")
            elif signals.couple_outcome == "xlinked_risk":
                fired_rules.append("TRI-T2-003")

        if signals.engine_category in ("xlinked_carrier", "xlinked_male"):
            fired_rules.append("TRI-T2-003")
        elif signals.engine_category == "possible_affected" and "TRI-T3-001" not in fired_rules:
            fired_rules.append("TRI-T2-002")

        # --- T1 Triggers ---
        if signals.couple_outcome == "incomplete":
            fired_rules.append("TRI-T1-001")
        if signals.teach_back_failed_twice:
            fired_rules.append("TRI-T1-002")
        if signals.reopen_count_48h > 3:
            fired_rules.append("TRI-T1-004")

        # --- T0 Triggers ---
        if not fired_rules:
            if signals.engine_category == "screen_negative":
                fired_rules.append("TRI-T0-001")
            else:
                fired_rules.append("TRI-T0-002")

        # Determine highest triggered tier
        highest_rule_tier = "T0"
        for r_id in fired_rules:
            tier_prefix = r_id.split("-")[1]
            if TIER_RANKS.get(tier_prefix, 0) > TIER_RANKS.get(highest_rule_tier, 0):
                highest_rule_tier = tier_prefix

        # Hard Rule: Tiers only escalate, never downgrade automatically!
        final_tier = max_tier(highest_rule_tier, signals.existing_case_tier)
        sla_due = compute_sla_due(final_tier)

        if final_tier == "T3":
            system_action = "urgent_callback_queue"
            safety_resources = True
        elif final_tier == "T2":
            system_action = "mandatory_counsellor_booking"
        elif final_tier == "T1":
            system_action = "offer_routine_booking"
        else:
            system_action = "self_serve_options"

        # Upsert or save case into database
        conn = self.db.get_connection()
        cur = conn.cursor()
        case_id = f"case_{uuid.uuid4().hex[:12]}"
        import json
        cur.execute("""
            INSERT INTO triage_case (id, person_id, tier, fired_rules, sla_due, state)
            VALUES (?, ?, ?, ?, ?, 'created')
        """, (case_id, signals.person_id, final_tier, json.dumps(fired_rules), sla_due))
        conn.commit()
        conn.close()

        # Audit log the triage decision
        self.audit.record_event(
            actor="system:triage_router",
            action="triage_routed",
            target=f"case:{case_id}",
        )

        return TriageDecision(
            case_id=case_id,
            person_id=signals.person_id,
            tier=final_tier,
            fired_rules=fired_rules,
            sla_due=sla_due,
            system_action=system_action,
            directive_handoff_message=directive_handoff,
            safety_resources_shown=safety_resources,
            state="created",
        )


router = TriageRouter()
