import pytest
import uuid
import datetime
from backend.database import Database


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_rls.db"
    db = Database(f"sqlite:///{db_file}")
    return db


def test_person_rls(test_db):
    p1 = "user_fatima"
    p2 = "user_tariq"
    
    assert test_db.can_read_person(p1, current_user_id=p1, role="patient") is True
    assert test_db.can_read_person(p1, current_user_id=p2, role="patient") is False
    assert test_db.can_read_person(p1, current_user_id="admin_01", role="admin") is True


def test_screening_result_rls(test_db):
    conn = test_db.get_connection()
    cur = conn.cursor()
    
    p1 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (p1, "auth_1", "Fatima", 1998, "F"))
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (p2, "auth_2", "Tariq", 1996, "M"))
    
    res1 = str(uuid.uuid4())
    cur.execute("INSERT INTO screening_result (id, person_id, panel_id, lab_id) VALUES (?, ?, ?, ?)",
                (res1, p1, "panel_uae_01", "lab_ad_01"))
    conn.commit()
    conn.close()

    assert test_db.can_read_screening_result(res1, current_user_id=p1, role="patient") is True
    assert test_db.can_read_screening_result(res1, current_user_id=p2, role="patient") is False
    assert test_db.can_read_screening_result(res1, current_user_id="admin", role="admin") is True


def test_couple_result_rls_mutual_consent_and_revocation(test_db):
    conn = test_db.get_connection()
    cur = conn.cursor()

    p_a = "partner_fatima"
    p_b = "partner_tariq"
    p_c = "intruder_person"

    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (p_a, "auth_a", "Fatima", 1998, "F"))
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (p_b, "auth_b", "Tariq", 1996, "M"))
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (p_c, "auth_c", "ThirdParty", 1995, "M"))

    link_id = "link_fatima_tariq"
    cur.execute("INSERT INTO couple_link (id, partner_a, partner_b, status) VALUES (?, ?, ?, ?)",
                (link_id, p_a, p_b, "active"))

    conn.commit()
    conn.close()

    # Step 1: No grants active -> access denied for both
    assert test_db.can_read_couple_result(link_id, current_user_id=p_a) is False
    assert test_db.can_read_couple_result(link_id, current_user_id=p_b) is False

    # Step 2: Partner A grants consent; Partner B has not yet granted
    conn = test_db.get_connection()
    cur = conn.cursor()
    grant_a = "grant_a"
    cur.execute("""
        INSERT INTO consent_grant (id, grantor, grantee, scope, purpose)
        VALUES (?, ?, ?, 'couple_result', 'Pre-marital compatibility check')
    """, (grant_a, p_a, p_b))
    conn.commit()
    conn.close()

    # Still denied for both because consent must be mutual!
    assert test_db.can_read_couple_result(link_id, current_user_id=p_a) is False
    assert test_db.can_read_couple_result(link_id, current_user_id=p_b) is False

    # Step 3: Partner B grants consent as well
    conn = test_db.get_connection()
    cur = conn.cursor()
    grant_b = "grant_b"
    cur.execute("""
        INSERT INTO consent_grant (id, grantor, grantee, scope, purpose)
        VALUES (?, ?, ?, 'couple_result', 'Pre-marital compatibility check')
    """, (grant_b, p_b, p_a))
    conn.commit()
    conn.close()

    # Now BOTH can read the couple result!
    assert test_db.can_read_couple_result(link_id, current_user_id=p_a) is True
    assert test_db.can_read_couple_result(link_id, current_user_id=p_b) is True
    # Third party user C CANNOT read it!
    assert test_db.can_read_couple_result(link_id, current_user_id=p_c) is False

    # Step 4: Partner A revokes consent
    conn = test_db.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE consent_grant SET revoked_at = datetime('now') WHERE id = ?", (grant_a,))
    conn.commit()
    conn.close()

    # Immediately hidden from BOTH partners!
    assert test_db.can_read_couple_result(link_id, current_user_id=p_a) is False
    assert test_db.can_read_couple_result(link_id, current_user_id=p_b) is False


def test_triage_case_rls(test_db):
    conn = test_db.get_connection()
    cur = conn.cursor()

    patient_id = "pat_01"
    other_patient = "pat_02"
    counsellor_id = "counsellor_dr_layla"
    other_counsellor = "counsellor_dr_ahmed"

    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (patient_id, "auth_p1", "Sarah", 1999, "F"))
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES (?, ?, ?, ?, ?)",
                (other_patient, "auth_p2", "Maryam", 2000, "F"))

    case_assigned = "case_assigned"
    cur.execute("""
        INSERT INTO triage_case (id, person_id, tier, assigned_to, state)
        VALUES (?, ?, 'T2', ?, 'booked')
    """, (case_assigned, patient_id, counsellor_id))

    case_open = "case_open"
    cur.execute("""
        INSERT INTO triage_case (id, person_id, tier, assigned_to, state)
        VALUES (?, ?, 'T1', NULL, 'created')
    """, (case_open, other_patient))

    conn.commit()
    conn.close()

    # Patient can see own case
    assert test_db.can_read_triage_case(case_assigned, current_user_id=patient_id, role="patient") is True
    # Patient cannot see another patient's case
    assert test_db.can_read_triage_case(case_open, current_user_id=patient_id, role="patient") is False

    # Assigned counsellor can view assigned case
    assert test_db.can_read_triage_case(case_assigned, current_user_id=counsellor_id, role="counsellor") is True
    # Unassigned counsellor cannot view booked case assigned to someone else
    assert test_db.can_read_triage_case(case_assigned, current_user_id=other_counsellor, role="counsellor") is False

    # Any counsellor can view open/unassigned cases in the intake queue
    assert test_db.can_read_triage_case(case_open, current_user_id=counsellor_id, role="counsellor") is True
    assert test_db.can_read_triage_case(case_open, current_user_id=other_counsellor, role="counsellor") is True
