import pytest
from explain.validator import ExplanationValidator
from explain.pipeline import ExplanationPipeline
from backend.database import Database


@pytest.fixture
def val():
    return ExplanationValidator()


@pytest.fixture
def test_pipeline(tmp_path):
    db_file = tmp_path / "explain_test.db"
    db = Database(f"sqlite:///{db_file}")
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO person (id, auth_id, name, dob_year, sex)
        VALUES ('p001', 'auth_p001', 'Test User', 1995, 'F')
    """)
    conn.commit()
    conn.close()
    return ExplanationPipeline(database=db)


def test_validator_clean_template_passes(val):
    source = (
        "Both you and your partner carry a changed copy of the HBB gene for Beta-thalassemia. "
        "In each pregnancy, there is a 1 in 4 chance of having an affected child, "
        "a 1 in 2 chance of having a healthy carrier child, and a 1 in 4 chance of having a child who is neither. "
        "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    )
    is_valid, errors, meta = val.validate(source, source, language="en")
    assert is_valid is True
    assert len(errors) == 0


def test_validator_catches_number_drift(val):
    source = "In each pregnancy, there is a 1 in 4 chance. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    # Bad LLM alters number to '1 in 10'
    bad_cand = "In each pregnancy, there is a 1 in 10 chance. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    
    is_valid, errors, meta = val.validate(bad_cand, source, language="en")
    assert is_valid is False
    assert any("Numeric drift" in e for e in errors)


def test_validator_catches_missing_disclaimer(val):
    source = "In each pregnancy, there is a 1 in 4 chance. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    # Candidate drops screening disclaimer
    bad_cand = "In each pregnancy, there is a 1 in 4 chance. [DRAFT - requires clinical sign-off]"
    
    is_valid, errors, meta = val.validate(bad_cand, source, language="en")
    assert is_valid is False
    assert any("Missing required screening disclaimer" in e for e in errors)


def test_validator_catches_directive_phrases(val):
    source = "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    
    # Directive English
    bad_en = "You should not marry because of this risk. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    is_valid_en, errors_en, _ = val.validate(bad_en, source, language="en")
    assert is_valid_en is False
    assert any("Banned phrase detected" in e for e in errors_en)

    # Directive Arabic
    bad_ar = "ننصح بعدم الزواج. هذا فحص استكشافي وليس تشخيصاً طبياً. [DRAFT - requires clinical sign-off]"
    is_valid_ar, errors_ar, _ = val.validate(bad_ar, source, language="ar")
    assert is_valid_ar is False
    assert any("Banned phrase detected" in e for e in errors_ar)


def test_validator_catches_stigmatising_phrases(val):
    source = "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    bad = "You carry a defective gene in your body. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    is_valid, errors, _ = val.validate(bad, source, language="en")
    assert is_valid is False
    assert any("defective gene" in e for e in errors)


def test_validator_catches_deterministic_phrases(val):
    source = "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    bad = "Your child will have a severe disease. This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    is_valid, errors, _ = val.validate(bad, source, language="en")
    assert is_valid is False
    assert any("your child will have" in e for e in errors)


def test_pipeline_fallback_on_bad_llm_injection(test_pipeline):
    slots = {"gene": "HBB", "condition_name": "Beta-thalassemia"}
    
    # Normal execution (template-only)
    res_clean = test_pipeline.generate_explanation(
        template_key="CARRIER_AR_SUMMARY",
        slots=slots,
        person_id="p001",
        language="en",
        reading_level="standard",
    )
    assert res_clean["is_valid"] is True
    assert res_clean["fallback_used"] is False

    # Injected adversarial LLM output with directive advice
    bad_llm_text = "You should not marry! This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"
    res_bad = test_pipeline.generate_explanation(
        template_key="CARRIER_AR_SUMMARY",
        slots=slots,
        person_id="p001",
        language="en",
        reading_level="standard",
        injected_llm_output=bad_llm_text,
    )
    assert res_bad["is_valid"] is False
    assert res_bad["fallback_used"] is True
    # The output MUST NOT contain the banned phrase because it fell back to the approved template!
    assert "You should not marry" not in res_bad["final_text"]
    assert "You carry one changed copy" in res_bad["final_text"]
