"""Tests verifying all audit remediation fixes."""

import yaml
from pathlib import Path

from backend.audit_log import AuditLogService
from backend.database import Database
from backend.family_notice import FamilyNoticeService
from backend.intent_classifier import IntentClassifier
from backend.scheduler import SchedulerService
from backend.service import PlatformService
from explain.templates.catalog import TEMPLATE_METADATA, get_template_entry


def test_b2_individual_rules_have_tier():
    """B2: Every rule in engine/rules/v1.yaml has an explicit tier and clinical_signoff."""
    rules_path = Path("engine/rules/v1.yaml")
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "clinical_signoff" in data
    assert "DRAFT" in data["clinical_signoff"] or "pending" in data["clinical_signoff"]
    for r in data["individual_rules"]:
        assert "tier" in r, f"Rule {r['id']} missing tier"
        assert r["tier"] in ["T0", "T1", "T2", "T3"]


def test_b8_consanguinity_statement_phrasing():
    """B8: Consanguinity statement describes figures as general birth defects without 'recessive condition'."""
    rules_path = Path("engine/rules/v1.yaml")
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    consang = data.get("consanguinity_statement")
    assert consang is not None

    en = consang["body_en"]
    assert "birth defects in general" in en.lower()
    assert "recessive condition" not in en.lower()
    assert "3-4%" in en
    assert "1.7 to 2.8" in en
    assert consang.get("clinical_review_flag") is True


def test_b4_untested_partner_incomplete_flag():
    """B4 / Service: get_person_input correctly identifies untested partner."""
    service = PlatformService()
    # person_104 has no screening result
    p_untested = service.get_person_input("person_104")
    assert p_untested.is_tested is False

    # person_001 has a screening result
    p_tested = service.get_person_input("person_001")
    assert p_tested.is_tested is True


def test_c7_user_access_history():
    """C7: User can view their own access history."""
    audit_svc = AuditLogService()
    history = audit_svc.get_user_access_history("person_001")
    assert isinstance(history, list)
    assert len(history) > 0
    first = history[0]
    assert "id" in first
    assert "actor" in first
    assert "action" in first
    assert "target" in first
    assert "hash" in first


def test_d1_template_metadata_catalog():
    """D1: Template metadata catalog exposes version and approved_by."""
    assert len(TEMPLATE_METADATA) >= 8
    entry = get_template_entry("CARRIER_AR_SUMMARY")
    assert entry is not None
    assert entry["version"] == "v1"
    assert entry["approved_by"] == "DRAFT - requires clinical sign-off"


def test_d9_intent_classifier_language_autodetection():
    """D9: Intent classifier auto-detects language when not explicitly provided."""
    classifier = IntentClassifier()
    ar_res = classifier.classify_intent("هل يجب أن نتزوج رغم النتيجة؟")
    assert ar_res["is_decision_question"] is True
    assert "القرار يعود لكما بالكامل" in ar_res["handoff_message"]

    en_res = classifier.classify_intent("Should we still get married despite this?")
    assert en_res["is_decision_question"] is True
    assert "never advise on personal relationship or marriage decisions" in en_res["handoff_message"]


def test_e8_scheduler_available_slots():
    """E8: Scheduler lists slots filtered by language, gender, and modality."""
    scheduler = SchedulerService()
    ar_female_slots = scheduler.list_available_slots(language="ar", gender="female", modality="video")
    assert len(ar_female_slots) > 0
    for s in ar_female_slots:
        assert "ar" in s["languages"]
        assert s["gender"] == "female"
        assert "video" in s["modalities"]


def test_e11_service_directory():
    """E11: Service directory table exists and has accredited facilities."""
    db = Database()
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT id, name_en, facility_type, location FROM service_directory")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    assert len(rows) >= 5
    names = [r["name_en"] for r in rows]
    assert "Sheikh Khalifa Medical City - Medical Genetics" in names
    assert "Fakih IVF Fertility Center - PGT-M Lab" in names


def test_e12_shareable_card():
    """E12: Family cascade shareable card generates neutral, educational summary without identifiers."""
    family_svc = FamilyNoticeService()
    card_ar = family_svc.generate_shareable_card("بيتا ثلاسيميا", "ar")
    assert "معلومات توعوية" in card_ar["card"]["title"]
    assert "حاملاً للصفة الوراثية لا يعني إصابتك" in card_ar["card"]["body"]
    assert card_ar["card"]["disclaimer"] == "هذا فحص استكشافي وليس تشخيصاً طبياً. [DRAFT - requires clinical sign-off]"
