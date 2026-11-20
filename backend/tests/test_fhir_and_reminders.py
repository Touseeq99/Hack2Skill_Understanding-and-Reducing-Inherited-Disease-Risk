import datetime

import pytest
from fastapi import HTTPException

from backend.audit_log import AuditLogService
from backend.database import Database
from backend.fhir_ingest import ingest_bundle, parse_bundle
from backend.reminders import process_missed_appointments
from backend.service import PlatformService


def _obs(gene, hgvs, zyg, sig):
    comp = lambda code, text: {"code": {"coding": [{"system": "http://loinc.org", "code": code}]}, "valueString": text}
    return {"resource": {"resourceType": "Observation", "component": [
        comp("48018-6", gene), comp("81290-9", hgvs), comp("53034-5", zyg), comp("53037-8", sig)]}}


def _bundle(patient="f1", rid="rep1", observations=()):
    return {"resourceType": "Bundle", "entry": [
        {"resource": {"resourceType": "DiagnosticReport", "id": rid, "subject": {"reference": f"Patient/{patient}"},
                      "performer": [{"reference": "Organization/lab_ad_01"}]}}, *observations]}


@pytest.fixture
def ctx(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'f.db'}")
    audit = AuditLogService(db)
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('f1','a','F',1995,'F')")
    conn.commit(); conn.close()
    return db, audit


def test_ingest_encrypts_drops_benign_and_engine_reads_it(ctx):
    db, audit = ctx
    out = ingest_bundle(db, audit, _bundle(observations=[
        _obs("HBB", "c.93-21G>A", "heterozygous", "Pathogenic"),
        _obs("CFTR", "c.1A>G", "heterozygous", "Benign")]), actor="lab_ad_01")
    assert out["variants_stored"] == 1 and out["benign_dropped"] == 1 and out["notification"] == "Your result is ready"
    svc = PlatformService(db); svc.audit = audit
    assert svc.get_individual_assessment("f1", "f1").category == "carrier"
    raw = db.get_connection().execute("SELECT gene FROM variant_call").fetchone()[0]
    assert raw == "[encrypted]"


def test_ingest_rejects_bad_input_and_duplicates(ctx):
    db, audit = ctx
    with pytest.raises(HTTPException) as e:
        parse_bundle(_bundle(observations=[_obs("NOTAGENE", "c.1A>G", "heterozygous", "Pathogenic")]))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        parse_bundle({"resourceType": "Patient"})
    assert e.value.status_code == 422
    ingest_bundle(db, audit, _bundle(observations=[]), actor="lab")
    with pytest.raises(HTTPException) as e:
        ingest_bundle(db, audit, _bundle(observations=[]), actor="lab")
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        ingest_bundle(db, audit, _bundle(patient="ghost", rid="r2"), actor="lab")
    assert e.value.status_code == 404


def test_only_lab_or_admin_can_import(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as main_mod
    monkeypatch.delenv("ALLOW_HEADER_AUTH", raising=False)
    c = TestClient(main_mod.app)
    tok = lambda uid: {"Authorization": "Bearer " + c.post("/api/auth/login", json={"user_id": uid, "otp": "123456"}).json()["access_token"]}
    assert c.post("/api/fhir/import", json={"resourceType": "Bundle"}, headers=tok("person_001")).status_code == 403
    assert c.post("/api/fhir/import", json={"resourceType": "Bundle"}, headers=tok("counsellor_maryam")).status_code == 403
    assert c.post("/api/fhir/import", json={"resourceType": "Bundle"}, headers=tok("lab_ad_01")).status_code == 422  # allowed, but invalid bundle


def test_missed_appointment_reminder_then_outreach_only_for_t2_t3(ctx):
    db, audit = ctx
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('f2','b','G',1995,'F')")
    conn.execute("INSERT INTO triage_case (id, person_id, tier, state) VALUES ('c_t2','f1','T2','booked')")
    conn.execute("INSERT INTO triage_case (id, person_id, tier, state) VALUES ('c_t1','f2','T1','booked')")
    slot = "2026-11-18T09:00:00Z"
    for cid in ("c_t2", "c_t1"):
        conn.execute("INSERT INTO appointment_booking (id, case_id, counsellor_id, slot_time, language_pref, modality, status) VALUES (?,?,?,?, 'ar','video','booked')", ("b_" + cid, cid, "counsellor_x", slot))
    conn.commit(); conn.close()

    t0 = datetime.datetime(2026, 11, 18, 12, 0, tzinfo=datetime.timezone.utc)
    assert process_missed_appointments(db, audit, now=t0) == {"gentle_reminders_created": 2, "counsellor_outreach_created": 0}
    assert process_missed_appointments(db, audit, now=t0) == {"gentle_reminders_created": 0, "counsellor_outreach_created": 0}  # idempotent

    t1 = t0 + datetime.timedelta(hours=49)
    assert process_missed_appointments(db, audit, now=t1) == {"gentle_reminders_created": 0, "counsellor_outreach_created": 1}
    c = db.get_connection()
    outreach = c.execute("SELECT case_id FROM reminder WHERE kind='counsellor_outreach'").fetchall()
    msgs = [r[0] for r in c.execute("SELECT message FROM reminder WHERE kind='gentle_reminder'").fetchall()]
    c.close()
    assert [r[0] for r in outreach] == ["c_t2"]                     # T1 gets only the reminder
    assert all("HBB" not in m and "carrier" not in m.lower() for m in msgs)  # reminders are content-free
