import pytest
from fastapi import HTTPException
import backend.main as main_mod
import backend.service as srv_mod
from backend.database import Database
from backend.service import PlatformService
from backend.audit_log import AuditLogService
from data.generate_seed import generate_cohort, seed_database


@pytest.fixture
def api_ctx(tmp_path):
    db_file = tmp_path / "test_api.db"
    test_db = Database(f"sqlite:///{db_file}")

    cohort = generate_cohort(seed=999)
    seed_database(test_db, cohort)

    test_audit = AuditLogService(test_db)
    test_service = PlatformService(test_db)
    test_service.audit = test_audit

    orig_db = main_mod.db
    orig_srv = main_mod.service
    orig_audit = main_mod.audit_logger

    main_mod.db = test_db
    main_mod.service = test_service
    main_mod.audit_logger = test_audit
    srv_mod.service = test_service

    yield {
        "db": test_db,
        "service": test_service,
        "audit": test_audit,
    }

    main_mod.db = orig_db
    main_mod.service = orig_srv
    main_mod.audit_logger = orig_audit
    srv_mod.service = orig_srv


def test_health_check_endpoint(api_ctx):
    res = main_mod.health_check()
    assert res["status"] == "healthy"
    assert res["audit_chain_valid"] is True
    assert res["engine_version"] == "v1"


def test_individual_result_and_rls(api_ctx):
    auth_fatima = {"user_id": "person_001", "role": "patient"}
    auth_other = {"user_id": "person_002", "role": "patient"}

    # Fatima viewing her own result
    res = main_mod.get_individual_result("person_001", auth=auth_fatima)
    assert res.category == "carrier"
    assert "HBB" in res.genes

    # Other patient attempting unauthorized access -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        main_mod.get_individual_result("person_001", auth=auth_other)
    assert exc_info.value.status_code == 403


def test_couple_mutual_consent_and_revocation(api_ctx):
    auth_fatima = {"user_id": "person_001", "role": "patient"}
    auth_partner_21 = {"user_id": "person_021", "role": "patient"}

    # Fatima & Tariq have active mutual grants for cpl_link_001
    res = main_mod.get_couple_result("cpl_link_001", is_consanguineous=False, auth=auth_fatima)
    assert res.outcome == "same_gene_match"
    assert res.tier == "T2"
    assert res.shared_genes == ["HBB"]
    assert res.natural_frequencies["affected"] == "1 in 4"

    # Couple 21 has only one-sided grant -> 403 Forbidden!
    with pytest.raises(HTTPException) as exc_info:
        main_mod.get_couple_result("cpl_link_021", is_consanguineous=False, auth=auth_partner_21)
    assert exc_info.value.status_code == 403

    # Revoking Fatima's grant immediately hides the couple result from both
    grant_id = "grant_person_001_cpl_link_001"
    rev = main_mod.revoke_consent(grant_id, auth=auth_fatima)
    assert rev["status"] == "revoked"

    # Now accessing couple result must immediately raise 403
    with pytest.raises(HTTPException) as exc_info2:
        main_mod.get_couple_result("cpl_link_001", is_consanguineous=False, auth=auth_fatima)
    assert exc_info2.value.status_code == 403


def test_audit_verify_endpoint(api_ctx):
    res = main_mod.verify_audit_log()
    assert res["valid"] is True
    assert "intact" in res["message"]


def test_quiz_and_app_endpoints(api_ctx):
    # Test /api/quiz/questions
    questions_ar = main_mod.get_quiz_questions(lang="ar")
    assert len(questions_ar) == 4
    assert "ماذا تعني" in questions_ar[0]["question"]

    questions_en = main_mod.get_quiz_questions(lang="en")
    assert len(questions_en) == 4
    assert "What does" in questions_en[0]["question"]

    # Test /api/quiz/submit
    submit_req = main_mod.QuizSubmitRequest(
        answers={
            "q1_carrier_meaning": "b",
            "q2_risk_vs_diagnosis": "a",
            "q3_same_gene_probability": "a",
            "q4_residual_risk": "b",
        },
        language="ar",
        base_tier="T0",
    )
    auth_fatima = {"user_id": "person_001", "role": "patient"}
    result = main_mod.submit_quiz_answers(submit_req, auth=auth_fatima)
    assert result["score"] == 100.0
    assert result["passed"] is True
    assert result["assigned_tier"] == "T0"

    # Test /app endpoint
    app_resp = main_mod.serve_user_app()
    assert str(app_resp.path).endswith("index.html")
