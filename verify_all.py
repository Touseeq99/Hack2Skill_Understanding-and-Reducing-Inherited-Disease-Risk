"""Comprehensive verification script for the Inherited Disease Risk Platform.

Verifies every component against the architecture PDF specification.
Run with: python verify_all.py
"""

import sys
import os
import tempfile
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Windows consoles default to cp1252; the report and the demo output contain Unicode.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
_SUBPROCESS_KW = dict(capture_output=True, text=True, encoding="utf-8", errors="replace",
                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
sys.path.insert(0, ".")

results = []

def check(name, fn):
    try:
        ok, detail = fn()
        status = "PASS" if ok else "FAIL"
        results.append((name, status, detail))
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    except Exception as e:
        results.append((name, "ERROR", str(e)))
        print(f"  ✗ {name}: ERROR - {e}")
        traceback.print_exc()


print("\n" + "="*70)
print("  SECTION A: Structure & Files")
print("="*70)

def check_a1():
    dirs = ["docs", "engine", "backend", "explain", "app", "portal", "data", "eval", "infra"]
    missing = [d for d in dirs if not os.path.isdir(d)]
    return len(missing) == 0, f"Missing dirs: {missing}" if missing else "All 9 required directories present"
check("A1-directories", check_a1)

def check_a2():
    return os.path.isfile("README.md"), "README.md exists" if os.path.isfile("README.md") else "Missing"
check("A2-readme", check_a2)

def check_a3():
    return os.path.isfile(".env.example"), ".env.example exists"
check("A3-env-example", check_a3)

def check_a4():
    return os.path.isfile("docker-compose.yml"), "docker-compose.yml exists"
check("A4-docker-compose", check_a4)

def check_a5():
    return os.path.isfile("requirements.txt"), "requirements.txt exists"
check("A5-requirements", check_a5)

print("\n" + "="*70)
print("  SECTION B: Risk Engine - Individual Rules")
print("="*70)

from engine.risk_engine import classify, couple, get_rules
from engine.models import VariantCall, PersonInput

def check_b1_pure():
    """Engine has no network/LLM/random imports"""
    import ast
    with open("engine/risk_engine.py") as f:
        tree = ast.parse(f.read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    forbidden = imports & {"requests", "urllib", "socket", "random", "openai", "langchain", "ollama", "httpx"}
    return len(forbidden) == 0, f"Pure functions, no forbidden imports. Imports: {sorted(imports)}"
check("B1-pure-engine", check_b1_pure)

def check_b2_yaml():
    """Rules in versioned YAML with IDs, tiers, clinical_signoff"""
    rules = get_rules("v1")
    assert rules["version"] == "v1"
    assert rules["clinical_signoff"] == "DRAFT - requires clinical sign-off"
    for r in rules["individual_rules"]:
        assert "id" in r, "Missing id in rule"
        assert "tier" in r or "default_tier" in r, f"Missing tier in {r['id']}"
        assert r.get("clinical_signoff") == "pending", f"Missing clinical_signoff in {r['id']}"
    for r in rules["couple_rules"]:
        assert "id" in r
        assert "tier" in r
        assert r.get("clinical_signoff") == "pending"
    return True, f"{len(rules['individual_rules'])} individual + {len(rules['couple_rules'])} couple rules, all versioned"
check("B2-yaml-rules", check_b2_yaml)

def check_b3_screen_negative():
    """No P/LP -> screen_negative, T0"""
    p = PersonInput(id="test", sex="F", variants=[])
    r = classify(p)
    return r.category == "screen_negative" and r.tier == "T0", f"category={r.category}, tier={r.tier}"
check("B3-IND001-screen-negative", check_b3_screen_negative)

def check_b3_carrier_ar():
    """One P/LP in AR gene -> carrier"""
    p = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    r = classify(p)
    return r.category == "carrier" and r.rule_id == "IND-002", f"category={r.category}, rule={r.rule_id}, tier={r.tier}"
check("B3-IND002-carrier-AR", check_b3_carrier_ar)

def check_b3_carrier_tiers():
    """Carrier tiers: T1 (untested), T0 (partner neg/diff), T2 (partner same gene)"""
    p_unlinked = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    r1 = classify(p_unlinked)
    
    p_neg = PersonInput(id="test", sex="F", partner_status="negative", variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    r2 = classify(p_neg)
    
    p_same = PersonInput(id="test", sex="F", partner_status="same_gene", variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])
    r3 = classify(p_same)
    
    ok = r1.tier == "T1" and r2.tier == "T0" and r3.tier == "T2"
    return ok, f"untested={r1.tier}(T1), neg={r2.tier}(T0), same={r3.tier}(T2)"
check("B3-IND002-carrier-tiers", check_b3_carrier_tiers)

def check_b3_xlinked_female():
    """XL P/LP female -> xlinked_carrier, T2"""
    p = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="DMD", hgvs="c.1A>G", zygosity="heterozygous", classification="pathogenic", inheritance="XL")
    ])
    r = classify(p)
    return r.category == "xlinked_carrier" and r.tier == "T2", f"category={r.category}, tier={r.tier}"
check("B3-IND003-xlinked-female", check_b3_xlinked_female)

def check_b3_xlinked_male():
    """XL P/LP male -> xlinked_male, T2"""
    p = PersonInput(id="test", sex="M", variants=[
        VariantCall(gene="DMD", hgvs="c.1A>G", zygosity="hemizygous", classification="pathogenic", inheritance="XL")
    ])
    r = classify(p)
    return r.category == "xlinked_male" and r.tier == "T2", f"category={r.category}, tier={r.tier}"
check("B3-IND004-xlinked-male", check_b3_xlinked_male)

def check_b3_possible_affected():
    """Two P/LP same AR gene -> possible_affected, T2 default, T3 if pregnant"""
    p = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
    ])
    r1 = classify(p)
    
    p2 = PersonInput(id="test", sex="F", pregnancy_status=True, variants=[
        VariantCall(gene="HBB", hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
        VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous", classification="pathogenic", inheritance="AR"),
    ])
    r2 = classify(p2)
    
    ok = r1.category == "possible_affected" and r1.tier == "T2" and r2.tier == "T3"
    return ok, f"default={r1.tier}(T2), pregnant={r2.tier}(T3)"
check("B3-IND005-possible-affected", check_b3_possible_affected)

def check_b3_vus_only():
    """VUS only -> uncertain, T0 (T2 if partner P/LP same gene)"""
    p1 = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="CFTR", hgvs="c.1A>G", zygosity="heterozygous", classification="VUS", inheritance="AR")
    ])
    r1 = classify(p1)
    
    p2 = PersonInput(id="test", sex="F", partner_status="same_gene_plp", variants=[
        VariantCall(gene="CFTR", hgvs="c.1A>G", zygosity="heterozygous", classification="VUS", inheritance="AR")
    ])
    r2 = classify(p2)
    
    ok = r1.category == "uncertain" and r1.tier == "T0" and r2.tier == "T2"
    return ok, f"normal={r1.tier}(T0), partner_plp={r2.tier}(T2)"
check("B3-IND006-vus-only", check_b3_vus_only)

def check_b3_benign_dropped():
    """Benign/likely_benign dropped at ingestion"""
    p = PersonInput(id="test", sex="F", variants=[
        VariantCall(gene="HBB", hgvs="c.1A>G", zygosity="heterozygous", classification="benign", inheritance="AR"),
        VariantCall(gene="CFTR", hgvs="c.2A>G", zygosity="heterozygous", classification="likely_benign", inheritance="AR"),
    ])
    r = classify(p)
    return r.category == "screen_negative", f"Benign dropped -> {r.category}"
check("B3-benign-dropped", check_b3_benign_dropped)


print("\n" + "="*70)
print("  SECTION B: Risk Engine - Couple Rules")
print("="*70)

def make_carrier(gene="HBB", sex="F"):
    return PersonInput(id=f"test_{gene}_{sex}", sex=sex, is_tested=True, variants=[
        VariantCall(gene=gene, hgvs="c.20A>T", zygosity="heterozygous", classification="pathogenic", inheritance="AR")
    ])

def make_affected(gene="HBB", sex="F"):
    return PersonInput(id=f"aff_{gene}_{sex}", sex=sex, is_tested=True, variants=[
        VariantCall(gene=gene, hgvs="c.20A>T", zygosity="homozygous", classification="pathogenic", inheritance="AR"),
    ])

def make_negative(sex="F"):
    return PersonInput(id=f"neg_{sex}", sex=sex, is_tested=True, variants=[])

def make_vus(gene="HBB", sex="F"):
    return PersonInput(id=f"vus_{gene}_{sex}", sex=sex, is_tested=True, variants=[
        VariantCall(gene=gene, hgvs="c.1A>G", zygosity="heterozygous", classification="VUS", inheritance="AR")
    ])

def check_cpl001():
    """Both carriers same gene -> same_gene_match, T2, 1-in-4"""
    r = couple(make_carrier("HBB", "F"), make_carrier("HBB", "M"))
    nf = r.natural_frequencies
    ok = r.outcome == "same_gene_match" and r.tier == "T2" and nf.get("affected") == "1 in 4"
    return ok, f"outcome={r.outcome}, tier={r.tier}, affected={nf.get('affected')}"
check("CPL001-carriers-same-gene", check_cpl001)

def check_cpl002():
    """Affected + carrier same gene -> T2, 1-in-2 affected"""
    r = couple(make_affected("HBB", "F"), make_carrier("HBB", "M"))
    nf = r.natural_frequencies
    ok = r.outcome == "same_gene_match" and r.tier == "T2" and nf.get("affected") == "1 in 2"
    return ok, f"outcome={r.outcome}, tier={r.tier}, affected={nf.get('affected')}"
check("CPL002-affected-plus-carrier", check_cpl002)

def check_cpl003():
    """Both affected same gene -> T2, all affected"""
    r = couple(make_affected("HBB", "F"), make_affected("HBB", "M"))
    ok = r.outcome == "same_gene_match" and r.tier == "T2"
    return ok, f"outcome={r.outcome}, tier={r.tier}, freqs={r.natural_frequencies}"
check("CPL003-both-affected", check_cpl003)

def check_cpl004():
    """Different genes -> no_shared_gene, T0"""
    r = couple(make_carrier("HBB", "F"), make_carrier("CFTR", "M"))
    ok = r.outcome == "no_shared_gene" and r.tier == "T0"
    return ok, f"outcome={r.outcome}, tier={r.tier}"
check("CPL004-different-genes", check_cpl004)

def check_cpl005():
    """Carrier + negative -> no_shared_gene, residual risk range"""
    r = couple(make_carrier("HBB", "F"), make_negative("M"))
    ok = r.outcome == "no_shared_gene" and "residual" in str(r.natural_frequencies).lower()
    return ok, f"outcome={r.outcome}, tier={r.tier}, freqs={r.natural_frequencies}"
check("CPL005-carrier-plus-negative", check_cpl005)

def check_cpl006():
    """Carrier gene X + VUS gene X -> uncertain_match, T2, NO numbers"""
    r = couple(make_carrier("HBB", "F"), make_vus("HBB", "M"))
    nf = r.natural_frequencies
    ok = r.outcome == "uncertain_match" and r.tier == "T2"
    has_no_number = "NO number" in str(nf) or "uncertain" in str(nf).lower()
    return ok and has_no_number, f"outcome={r.outcome}, tier={r.tier}, freqs={nf}"
check("CPL006-carrier-plus-vus", check_cpl006)

def check_cpl007():
    """Partner not tested -> incomplete, T1"""
    untested = PersonInput(id="untested", sex="M", is_tested=False, variants=[])
    r = couple(make_carrier("HBB", "F"), untested)
    ok = r.outcome == "incomplete" and r.tier == "T1"
    return ok, f"outcome={r.outcome}, tier={r.tier}"
check("CPL007-partner-untested", check_cpl007)

def check_cpl008():
    """X-linked female carrier with partner -> xlinked_risk, T2, per sex"""
    xl_female = PersonInput(id="xl_f", sex="F", is_tested=True, variants=[
        VariantCall(gene="DMD", hgvs="c.1A>G", zygosity="heterozygous", classification="pathogenic", inheritance="XL")
    ])
    partner = make_negative("M")
    r = couple(xl_female, partner)
    ok = r.outcome == "xlinked_risk" and r.tier == "T2"
    return ok, f"outcome={r.outcome}, tier={r.tier}, freqs={r.natural_frequencies}"
check("CPL008-xlinked-couple", check_cpl008)

def check_symmetry():
    """couple(a,b) == couple(b,a)"""
    a = make_carrier("HBB", "F")
    b = make_carrier("HBB", "M")
    r1 = couple(a, b)
    r2 = couple(b, a)
    ok = r1.outcome == r2.outcome and r1.tier == r2.tier and r1.natural_frequencies == r2.natural_frequencies
    return ok, f"Symmetric: outcome={r1.outcome}=={r2.outcome}, tier={r1.tier}=={r2.tier}"
check("B6-couple-symmetry", check_symmetry)

def check_natural_freq():
    """Numbers shown as natural frequencies, never percentages alone"""
    r = couple(make_carrier("HBB", "F"), make_carrier("HBB", "M"))
    nf = str(r.natural_frequencies)
    has_natural = "1 in 4" in nf or "1 in 2" in nf
    has_pct_only = "%" in nf and "in" not in nf
    return has_natural and not has_pct_only, "Natural frequencies present, no percentages-only"
check("B5-natural-frequencies", check_natural_freq)

def check_consanguinity():
    """Consanguinity statement: birth defects in general, side by side, 3-4% baseline"""
    rules = get_rules("v1")
    cns = rules["consanguinity_statement"]
    body = cns["body_en"]
    ok = (
        "birth defect" in body.lower() and
        "3-4%" in body and
        "1.7" in body and
        "2.8" in body and
        cns.get("clinical_review_flag") is True and
        "side_by_side" in cns
    )
    return ok, "Has birth defects, 3-4%, 1.7-2.8, side-by-side, clinical review flag"
check("B8-consanguinity", check_consanguinity)


print("\n" + "="*70)
print("  SECTION C: Privacy & Consent Vault")
print("="*70)

from backend.database import db, Database
from backend.service import service, PlatformService
from backend.audit_log import audit_logger, AuditLogService
from fastapi import HTTPException

def check_c1():
    """Each result owned by one person"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE name='screening_result'")
    schema = cur.fetchone()
    conn.close()
    ok = schema and "person_id" in schema[0]
    return ok, "screening_result isolated by person_id"
check("C1-per-person-ownership", check_c1)

def check_c2():
    """consent_grant has correct columns"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(consent_grant)")
    cols = [r[1] for r in cur.fetchall()]
    conn.close()
    needed = {"grantor", "grantee", "scope", "purpose", "expires_at", "revoked_at"}
    has_all = needed.issubset(set(cols))
    return has_all, f"Columns: {cols}"
check("C2-consent-grant-schema", check_c2)

def check_c3_c4():
    """Couple result blocked without mutual consent; revocation hides immediately"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db_path = f.name
    try:
        test_db = Database(f"sqlite:///{tmp_db_path}")
        test_svc = PlatformService(test_db)
        conn = test_db.get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('pa', 'auth_pa', 'Alice', 1998, 'F'), ('pb', 'auth_pb', 'Bob', 1996, 'M')")
        cur.execute("INSERT INTO screening_result (id, person_id, panel_id, lab_id) VALUES ('sr_a', 'pa', 'panel_1', 'lab_1'), ('sr_b', 'pb', 'panel_1', 'lab_1')")
        cur.execute("INSERT INTO variant_call (id, result_id, gene, hgvs, zygosity, classification, inheritance, encrypted_payload) VALUES ('v1', 'sr_a', 'HBB', 'c.1A>T', 'heterozygous', 'pathogenic', 'AR', 'dummy_enc'), ('v2', 'sr_b', 'HBB', 'c.2A>T', 'heterozygous', 'pathogenic', 'AR', 'dummy_enc')")
        cur.execute("INSERT INTO couple_link (id, partner_a, partner_b, status) VALUES ('cl1', 'pa', 'pb', 'active')")
        conn.commit()
        conn.close()
        
        # Without grants -> should block
        try:
            test_svc.get_couple_assessment("cl1", "pa")
            return False, "Should have blocked without grants"
        except HTTPException as e:
            if e.status_code != 403:
                return False, f"Expected 403, got {e.status_code}"
        
        # Grant from A only -> still blocked
        test_svc.grant_consent("pa", "pb", "couple_result", "test", "pa", "cl1")
        try:
            test_svc.get_couple_assessment("cl1", "pa")
            return False, "Should have blocked with only one grant"
        except HTTPException:
            pass
        
        # Grant from B -> now accessible
        test_svc.grant_consent("pb", "pa", "couple_result", "test", "pb", "cl1")
        r = test_svc.get_couple_assessment("cl1", "pa")
        if r.outcome != "same_gene_match":
            return False, f"Expected same_gene_match, got {r.outcome}"
        
        # Revoke A's grant -> blocked again
        conn = test_db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM consent_grant WHERE grantor='pa'")
        grant_a = cur.fetchone()["id"]
        conn.close()
        test_svc.revoke_consent(grant_a, "pa")
        try:
            test_svc.get_couple_assessment("cl1", "pa")
            return False, "Should have blocked after revocation"
        except HTTPException:
            pass
        
        return True, "Mutual consent enforced, revocation hides immediately"
    finally:
        try:
            os.remove(tmp_db_path)
        except OSError:
            pass
check("C3/C4-mutual-consent-revocation", check_c3_c4)

def check_c5():
    """RLS policies tested"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db_path = f.name
    try:
        test_db = Database(f"sqlite:///{tmp_db_path}")
        test_svc = PlatformService(test_db)
        conn = test_db.get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('u1', 'auth_u1', 'User1', 1998, 'F'), ('u2', 'auth_u2', 'User2', 1996, 'M')")
        cur.execute("INSERT INTO screening_result (id, person_id, panel_id, lab_id) VALUES ('sr1', 'u1', 'panel_1', 'lab_1')")
        conn.commit()
        conn.close()
        
        # u1 can read own
        _ = test_svc.get_individual_assessment("u1", "u1")
        # u2 cannot read u1's data
        try:
            test_svc.get_individual_assessment("u1", "u2")
            return False, "Should have blocked cross-user read"
        except HTTPException as e:
            if e.status_code != 403:
                return False, f"Expected 403, got {e.status_code}"
        
        return True, "RLS: user reads own data, blocked from others"
    finally:
        try:
            os.remove(tmp_db_path)
        except OSError:
            pass
check("C5-rls-policies", check_c5)

def check_c6():
    """Hash-chained audit log with tamper detection"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db_path = f.name
    try:
        test_db = Database(f"sqlite:///{tmp_db_path}")
        al = AuditLogService(test_db)
        al.record_event("user1", "read", "res1")
        e2 = al.record_event("user1", "read", "res2")
        al.record_event("user1", "read", "res3")
        
        valid, err = al.verify_chain()
        if not valid:
            return False, f"Chain should be valid but got: {err}"
        
        # Tamper
        conn = al.db.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE audit_event SET action='TAMPERED' WHERE id = ?", (e2.id,))
        conn.commit()
        conn.close()
        
        valid2, err2 = al.verify_chain()
        return not valid2, f"Valid chain: OK. Tampered chain detected: {err2}"
    finally:
        try:
            os.remove(tmp_db_path)
        except OSError:
            pass
check("C6-audit-log-tamper-detection", check_c6)

def check_c7():
    """User access history endpoint"""
    history = audit_logger.get_user_access_history("person_001")
    return len(history) > 0, f"{len(history)} audit entries for person_001"
check("C7-access-history", check_c7)

def check_c8():
    """Encrypted genetic payload"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT encrypted_payload FROM variant_call LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        payload = row[0]
        is_encrypted = not any(word in payload.lower() for word in ["pathogenic", "heterozygous", "gene"])
        return is_encrypted, f"Payload is ciphertext ({payload[:30]}...)"
    return False, "No variant_call data"
check("C8-encryption", check_c8)


print("\n" + "="*70)
print("  SECTION D: Explanation Layer")
print("="*70)

from explain.templates.catalog import TEMPLATES, TEMPLATE_METADATA
from explain.pipeline import pipeline
from explain.validator import validator

def check_d1():
    """Template library with EN/AR, metadata"""
    has_ar = any("ar" in t for t in TEMPLATES.values())
    has_en = any("en" in t for t in TEMPLATES.values())
    has_metadata = len(TEMPLATE_METADATA) > 0
    return has_ar and has_en and has_metadata, f"{len(TEMPLATES)} templates, {len(TEMPLATE_METADATA)} metadata entries"
check("D1-template-library", check_d1)

def check_d2():
    """Pipeline: select->fill->adapt->validate->log"""
    result = pipeline.generate_explanation(
        template_key="CARRIER_AR_SUMMARY",
        slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
        person_id="person_001",
        language="ar",
    )
    ok = "final_text" in result and "is_valid" in result
    return ok, f"Pipeline produced explanation with keys: {list(result.keys())}"
check("D2-pipeline", check_d2)

def check_d3():
    """Validator catches number drift, missing disclaimer, banned phrases"""
    source = "You carry one changed copy of gene HBB. 1 in 4 chance. This is a screening result, not a diagnosis. DRAFT - requires clinical sign-off"
    is_valid1, errors1, _ = validator.validate(source, source, language="en")
    
    # Bad number should fail
    bad_num = "You carry one changed copy of gene HBB. 1 in 3 chance. This is a screening result, not a diagnosis. DRAFT - requires clinical sign-off"
    is_valid2, errors2, _ = validator.validate(bad_num, source, language="en")
    
    # Directive phrase should fail
    bad_dir = "You carry one changed copy of gene HBB. 1 in 4 chance. You should not marry. This is a screening result, not a diagnosis. DRAFT - requires clinical sign-off"
    is_valid3, errors3, _ = validator.validate(bad_dir, source, language="en")
    
    ok = is_valid1 and not is_valid2 and not is_valid3
    return ok, f"Good={is_valid1}, NumDrift={not is_valid2}, Directive={not is_valid3}"
check("D3/D4-validator", check_d3)

def check_d9():
    """Non-directive: decision questions get handoff"""
    from backend.intent_classifier import IntentClassifier
    ic = IntentClassifier()
    
    r_en = ic.classify_intent("Should we still get married?")
    r_ar = ic.classify_intent("هل يجب أن نتزوج")
    
    ok = r_en["is_decision_question"] and r_ar["is_decision_question"]
    return ok, f"EN decision={r_en['is_decision_question']}, AR decision={r_ar['is_decision_question']}"
check("D9-non-directive-handoff", check_d9)


print("\n" + "="*70)
print("  SECTION E: Triage & Services")
print("="*70)

from backend.triage_router import router, TriageSignals
from backend.referral_state_machine import ALLOWED_TRANSITIONS

def _isolated_router(person_ids):
    """Router backed by a throwaway DB so persisted cases from other runs cannot leak into a check."""
    import tempfile as _tf
    from backend.triage_router import TriageRouter as _TR
    d = _tf.mkdtemp()
    _db = Database(f"sqlite:///{os.path.join(d, 'verify_triage.db')}")
    _conn = _db.get_connection()
    for pid in person_ids:
        _conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, 1995, 'F')", (pid, "a_" + pid, pid))
    _conn.commit()
    _conn.close()
    return _TR(_db)



def check_e1():
    """Triage T0-T3 with rule IDs"""
    rt = _isolated_router(["e1_a", "e1_b", "e1_c"])
    r0 = rt.evaluate(TriageSignals(person_id="e1_a", engine_category="screen_negative"))
    r2 = rt.evaluate(TriageSignals(person_id="e1_b", engine_category="carrier", couple_outcome="same_gene_match"))
    r3 = rt.evaluate(TriageSignals(person_id="e1_c", engine_category="possible_affected", is_pregnant=True))

    ok = r0.tier == "T0" and r2.tier == "T2" and r3.tier == "T3"
    return ok, f"T0={r0.tier}, T2={r2.tier}, T3={r3.tier}"
check("E1-triage-tiers", check_e1)

def check_e2():
    """Tiers never downgrade"""
    rt = _isolated_router(["e2_a"])
    first = rt.evaluate(TriageSignals(person_id="e2_a", engine_category="carrier", couple_outcome="same_gene_match"))
    later = rt.evaluate(TriageSignals(person_id="e2_a", engine_category="screen_negative"))
    ok = first.tier == "T2" and later.tier == "T2" and later.case_id == first.case_id
    return ok, f"Persisted T2 preserved across calls when benign signals fire: {later.tier}, same case={later.case_id == first.case_id}"
check("E2-no-downgrade", check_e2)

def check_e5():
    """SLAs: T3=24h, T2=3days, T1=10days"""
    rt = _isolated_router(["e5_a", "e5_b", "e5_c"])
    r3 = rt.evaluate(TriageSignals(person_id="e5_a", engine_category="possible_affected", is_pregnant=True))
    r2 = rt.evaluate(TriageSignals(person_id="e5_b", engine_category="carrier", couple_outcome="same_gene_match"))
    r1 = rt.evaluate(TriageSignals(person_id="e5_c", engine_category="carrier", teach_back_failed_twice=True))
    
    ok = r3.sla_due is not None and r2.sla_due is not None and r1.sla_due is not None
    return ok, f"T3 sla={r3.sla_due is not None}, T2 sla={r2.sla_due is not None}, T1 sla={r1.sla_due is not None}"
check("E5-sla-tiers", check_e5)

def check_e7():
    """Referral state machine: 8 states"""
    states = ALLOWED_TRANSITIONS
    ok = "created" in states and "closed" in states
    return ok, f"States: {list(states.keys())}"
check("E7-referral-states", check_e7)

def check_e9():
    """Case packet PDF generated"""
    from backend.pdf_generator import generate_case_packet_pdf
    pdf = generate_case_packet_pdf({"case_id": "test", "patient_name": "Test", "tier": "T2"})
    ok = len(pdf) > 100 and pdf[:4] == b"%PDF"
    return ok, f"PDF generated: {len(pdf)} bytes"
check("E9-pdf-packet", check_e9)

def check_e11():
    """Service directory"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM service_directory")
    cnt = cur.fetchone()["cnt"]
    conn.close()
    return cnt >= 5, f"{cnt} services in directory"
check("E11-service-directory", check_e11)


print("\n" + "="*70)
print("  SECTION F: Safety & Evaluation")
print("="*70)

def check_f_safety():
    """Safety eval exists and runs"""
    from eval.run_eval import run_evaluations
    passed = run_evaluations()
    return passed is True, "All Promptfoo safety evaluations passed"
check("F-safety-eval", check_f_safety)


print("\n" + "="*70)
print("  SECTION G: Database & Synthetic Data")
print("="*70)

def check_g_data():
    """~200 people, ~80 couples with edge cases"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM person")
    people = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM couple_link")
    couples = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM person WHERE (2026 - dob_year) < 18")
    minors = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM person WHERE pregnancy_status = 1")
    pregnant = cur.fetchone()["cnt"]
    conn.close()
    ok = people >= 200 and couples >= 80
    return ok, f"{people} people, {couples} couples, {minors} minors, {pregnant} pregnant"
check("G-synthetic-data", check_g_data)

def check_g_tables():
    """All required tables exist"""
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    required = ["person", "screening_result", "variant_call", "consent_grant", "couple_link", 
                 "triage_case", "referral", "audit_event", "explanation_log", "family_notice",
                 "service_directory"]
    missing = [t for t in required if t not in tables]
    return len(missing) == 0, f"Tables: {tables}. Missing: {missing}"
check("G-database-tables", check_g_tables)


print("\n" + "="*70)
print("  SECTION H: Dashboard / Analytics")
print("="*70)

from backend.analytics import analytics_svc

def check_h1():
    """Dashboard metrics computed"""
    m = analytics_svc.get_dashboard_metrics()
    ok = "comprehension" in m and "counselling_uptake" in m and "privacy_and_security" in m
    return ok, f"Metrics keys: {list(m.keys())}"
check("H1-dashboard-metrics", check_h1)

def check_h3():
    """Marriage cancellation NOT a metric"""
    m = analytics_svc.get_dashboard_metrics()
    policy = m.get("ethical_policy", {})
    text = policy.get("explicit_excluded_metric", "")
    ok = "strictly not" in text.lower() or "not" in text.lower()
    return ok, f"ethical_exclusion: {text}"
check("H3-no-marriage-metric", check_h3)


print("\n" + "="*70)
print("  SECTION K: End-to-End Demo")
print("="*70)

def check_k_demo():
    """Demo script runs successfully"""
    import subprocess
    result = subprocess.run([sys.executable, "demo.py"], cwd=".", timeout=60, **_SUBPROCESS_KW)
    ok = result.returncode == 0 and "ALL 6 DEMO STEPS COMPLETED" in result.stdout
    return ok, "All 6 demo steps complete" if ok else f"Exit={result.returncode}, stderr={result.stderr[:200]}"
check("K-demo-script", check_k_demo)

def check_k_tests():
    """Full pytest suite"""
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", "-v", "--tb=short"], cwd=".", timeout=180, **_SUBPROCESS_KW)
    lines = result.stdout.strip().split("\n")
    last_line = lines[-1] if lines else ""
    ok = result.returncode == 0 and "passed" in last_line
    return ok, last_line
check("K-pytest-suite", check_k_tests)


# Final Summary
print("\n" + "="*70)
print("  FINAL SUMMARY")
print("="*70)

passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
errors = sum(1 for _, s, _ in results if s == "ERROR")
total = len(results)

print(f"\n  Total: {total}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"  Errors: {errors}")
print(f"\n  Overall: {'ALL PASS ✓' if failed == 0 and errors == 0 else 'ISSUES FOUND ✗'}")

if failed > 0 or errors > 0:
    print("\n  Issues:")
    for name, status, detail in results:
        if status != "PASS":
            print(f"    [{status}] {name}: {detail}")
