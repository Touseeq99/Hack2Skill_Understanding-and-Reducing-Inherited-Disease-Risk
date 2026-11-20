import pytest
from backend.database import Database
from backend.audit_log import AuditLogService


@pytest.fixture
def audit_svc(tmp_path):
    db_file = tmp_path / "test_audit.db"
    db = Database(f"sqlite:///{db_file}")
    return AuditLogService(db)


def test_audit_log_empty_chain_verifies(audit_svc):
    valid, err = audit_svc.verify_chain()
    assert valid is True
    assert err is None


def test_audit_log_chain_records_and_verifies(audit_svc):
    e1 = audit_svc.record_event(actor="person_001", action="read", target="result:scr_person_001")
    e2 = audit_svc.record_event(actor="person_001", action="grant_created", target="grant:cpl_001", grant_id="grant_123")
    e3 = audit_svc.record_event(actor="system", action="match", target="couple:cpl_001")

    assert e1.prev_hash == AuditLogService.GENESIS_HASH
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash

    valid, err = audit_svc.verify_chain()
    assert valid is True
    assert err is None


def test_audit_log_detects_data_tampering(audit_svc):
    audit_svc.record_event(actor="person_001", action="read", target="result:scr_001")
    e2 = audit_svc.record_event(actor="person_002", action="grant_revoked", target="grant:g_002")
    audit_svc.record_event(actor="system", action="match", target="couple:cpl_001")

    # Tamper with row e2 in database
    conn = audit_svc.db.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE audit_event SET action = 'tampered_action' WHERE id = ?", (e2.id,))
    conn.commit()
    conn.close()

    valid, err = audit_svc.verify_chain()
    assert valid is False
    assert "Tampered record" in err


def test_audit_log_detects_broken_chain(audit_svc):
    _ = audit_svc.record_event(actor="person_001", action="read", target="result:scr_001")
    e2 = audit_svc.record_event(actor="person_002", action="read", target="result:scr_002")

    # Tamper with prev_hash
    conn = audit_svc.db.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE audit_event SET prev_hash = 'bad_hash' WHERE id = ?", (e2.id,))
    conn.commit()
    conn.close()

    valid, err = audit_svc.verify_chain()
    assert valid is False
    assert "Broken chain" in err


def test_concurrent_writers_do_not_fork_the_chain(tmp_path):
    import threading
    from backend.database import Database
    from backend.audit_log import AuditLogService as AuditLogger
    logger = AuditLogger(Database(f"sqlite:///{tmp_path / 'race.db'}"))

    def work(n):
        for i in range(15):
            logger.record_event(actor=f"w{n}", action="read", target=f"t{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert logger.verify_chain() == (True, None)
