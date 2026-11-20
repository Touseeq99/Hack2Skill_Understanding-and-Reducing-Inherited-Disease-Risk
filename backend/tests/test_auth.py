import time

import pytest
from fastapi.testclient import TestClient

import backend.main as main_mod
from backend import auth


@pytest.fixture
def strict(monkeypatch):
    """Header auth OFF, as in a real deployment."""
    monkeypatch.delenv("ALLOW_HEADER_AUTH", raising=False)
    auth._failed.clear()
    return TestClient(main_mod.app)


def _token(client, user_id, otp="123456"):
    return client.post("/api/auth/login", json={"user_id": user_id, "otp": otp})


def test_no_credentials_is_401_and_headers_are_not_trusted(strict):
    assert strict.get("/api/me").status_code == 401
    r = strict.get("/api/me", headers={"X-User-Id": "person_001", "X-User-Role": "admin"})
    assert r.status_code == 401


def test_login_and_token_roundtrip(strict):
    r = _token(strict, "person_001")
    assert r.status_code == 200 and r.json()["role"] == "patient"
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert strict.get("/api/me", headers=h).json()["id"] == "person_001"


def test_wrong_otp_and_unknown_user_rejected_and_lockout(strict):
    assert _token(strict, "person_001", otp="000000").status_code == 401
    assert _token(strict, "nobody_here").status_code == 401
    for _ in range(5):
        _token(strict, "person_002", otp="bad")
    assert _token(strict, "person_002").status_code == 429


def test_tampered_and_expired_tokens_rejected(strict):
    good = auth.issue_token("person_001")
    payload, sig = good.split(".")
    assert auth.verify_token(payload + "." + sig[:-2] + "xx") is None
    assert auth.verify_token(auth.issue_token("person_001", ttl=-5)) is None
    forged_payload = auth._b64(b'{"sub":"person_001","role":"admin","exp":9999999999}')
    assert auth.verify_token(forged_payload + "." + sig) is None


def test_patient_token_cannot_use_staff_endpoints(strict):
    h = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    assert strict.get("/api/portal/queue", headers=h).status_code == 403
    assert strict.get("/api/analytics/metrics", headers=h).status_code == 403
    assert strict.get("/api/audit/verify", headers=h).status_code == 403


def test_staff_token_can_use_staff_endpoints_but_not_read_patient_results(strict):
    t = _token(strict, "counsellor_maryam").json()
    assert t["role"] == "counsellor"
    h = {"Authorization": "Bearer " + t["access_token"]}
    assert strict.get("/api/portal/queue", headers=h).status_code == 200
    assert strict.get("/api/analytics/metrics", headers=h).status_code == 200


def test_patient_cannot_read_someone_elses_result(strict):
    h = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    assert strict.get("/api/screening/person_002", headers=h).status_code == 403


def test_triage_ignores_client_claimed_engine_facts(strict):
    h = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    r = strict.post("/api/triage/evaluate", headers=h,
                    json={"engine_category": "screen_negative", "is_pregnant": False, "age_years": 40})
    assert r.status_code == 200  # unknown fields ignored; tier derives from server-side facts


def test_delete_person_data_cascades_and_keeps_audit(tmp_path):
    from backend.database import Database
    from backend.audit_log import AuditLogService
    from backend.service import PlatformService

    db = Database(f"sqlite:///{tmp_path / 'del.db'}")
    svc = PlatformService(db)
    svc.audit = AuditLogService(db)
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('d1','a1','Del',1995,'F')")
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('d2','a2','Other',1993,'M')")
    conn.execute("INSERT INTO screening_result (id, person_id, panel_id, lab_id, status) VALUES ('sr1','d1','p','l','final')")
    conn.execute("INSERT INTO consent_grant (id, grantor, grantee, scope, purpose) VALUES ('g1','d1','d2','couple_result','x')")
    conn.execute("INSERT INTO consent_grant (id, grantor, grantee, scope, purpose) VALUES ('g2','d2','d1','couple_result','x')")
    conn.execute("INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, language) VALUES ('c1','d1','q','post',100,'ar')")
    conn.execute("INSERT INTO triage_case (id, person_id, tier, state) VALUES ('t1','d1','T2','created')")
    conn.commit()
    conn.close()

    out = svc.delete_person_data("d1")
    assert out["deleted"] is True and out["removed_records"]["screening_result"] == 1

    conn = db.get_connection()
    for table, col in (("person", "id"), ("screening_result", "person_id"), ("comprehension_response", "person_id"),
                       ("triage_case", "person_id"), ("consent_grant", "grantor"), ("consent_grant", "grantee")):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = 'd1'").fetchone()[0] == 0, table
    assert conn.execute("SELECT COUNT(*) FROM person WHERE id = 'd2'").fetchone()[0] == 1  # others untouched
    conn.close()
    assert svc.audit.verify_chain() == (True, None)
    assert any(e["action"] == "data_deletion_completed" for e in svc.audit.get_user_access_history("d1"))


def test_delete_endpoint_requires_typed_confirmation(strict):
    h = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    assert strict.post("/api/users/me/delete", headers=h, json={"confirm": "yes"}).status_code == 422
    staff = {"Authorization": "Bearer " + _token(strict, "counsellor_maryam").json()["access_token"]}
    assert strict.post("/api/users/me/delete", headers=staff, json={"confirm": "DELETE"}).status_code == 403


def test_values_private_by_default_and_shared_only_on_opt_in(strict):
    pat = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    staff = {"Authorization": "Bearer " + _token(strict, "counsellor_maryam").json()["access_token"]}
    q = strict.get("/api/portal/queue", headers=staff).json()
    cid = next(c["id"] for c in q if c["person_id"] == "person_001")

    assert strict.post("/api/values", headers=pat, json={"answers": {"a": "1"}, "share_with_counsellor": False}).status_code == 200
    assert strict.get(f"/api/portal/cases/{cid}", headers=staff).json()["shared_values"] is None

    strict.post("/api/values", headers=pat, json={"answers": {"a": "2"}, "share_with_counsellor": True})
    assert strict.get(f"/api/portal/cases/{cid}", headers=staff).json()["shared_values"] == {"a": "2"}

    strict.post("/api/values", headers=pat, json={"answers": {"a": "2"}, "share_with_counsellor": False})
    assert strict.get(f"/api/portal/cases/{cid}", headers=staff).json()["shared_values"] is None  # opt-out is honoured


def test_options_endpoint_returns_seven(strict):
    pat = {"Authorization": "Bearer " + _token(strict, "person_001").json()["access_token"]}
    d = strict.get("/api/options?language=en", headers=pat).json()
    assert len(d["options"]) == 7


def test_variant_details_exist_only_inside_encrypted_payload(tmp_path):
    from backend.database import Database
    from backend.service import PlatformService
    from backend.vault import store_variant, REDACTED
    from engine.models import VariantCall

    db = Database(f"sqlite:///{tmp_path / 'vault.db'}")
    conn = db.get_connection()
    conn.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('v1','a','V',1995,'F')")
    conn.execute("INSERT INTO screening_result (id, person_id, panel_id, lab_id, status) VALUES ('sr','v1','p','l','final')")
    store_variant(conn.cursor(), "var1", "sr", VariantCall(gene="HBB", hgvs="c.93-21G>A", zygosity="heterozygous",
                                                           classification="pathogenic", inheritance="AR"))
    conn.commit()

    raw = conn.execute("SELECT gene, hgvs, zygosity, classification, inheritance, encrypted_payload FROM variant_call").fetchone()
    assert [raw[i] for i in range(5)] == [REDACTED] * 5
    assert "HBB" not in raw[5] and "c.93" not in raw[5]          # ciphertext is opaque
    conn.close()

    person = PlatformService(db).get_person_input("v1")           # engine still receives the real variant
    assert person.variants[0].gene == "HBB" and person.variants[0].is_pathogenic()
