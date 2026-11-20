"""Database access layer supporting PostgreSQL and SQLite fallback.
Provides explicit Row-Level Security (RLS) enforcement and data repository methods.
"""

import os
import sqlite3
from typing import Optional

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///inheritance_platform.db")


class Database:
    """Database connection and query engine with RLS enforcement."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self.is_sqlite = "sqlite" in self.db_url or not self.db_url.startswith("postgres")
        if self.is_sqlite:
            if self.db_url.startswith("sqlite:///"):
                self.sqlite_path = self.db_url.replace("sqlite:///", "")
            elif self.db_url.startswith("sqlite://"):
                self.sqlite_path = self.db_url.replace("sqlite://", "")
            else:
                self.sqlite_path = "inheritance_platform.db"
        else:
            self.sqlite_path = ""
        self._init_db()

    def get_connection(self):
        if self.is_sqlite:
            conn = sqlite3.connect(self.sqlite_path, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        else:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _init_db(self):
        """Create tables if they do not exist."""
        conn = self.get_connection()
        cur = conn.cursor()

        if self.is_sqlite:
            # SQLite schema equivalent to 001_initial_schema.sql
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS person (
                id TEXT PRIMARY KEY,
                auth_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'ar',
                literacy_pref TEXT NOT NULL DEFAULT 'standard',
                dob_year INTEGER NOT NULL,
                sex TEXT NOT NULL CHECK (sex IN ('F', 'M')),
                pregnancy_status BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS screening_result (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                panel_id TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                received_at TEXT DEFAULT CURRENT_TIMESTAMP,
                fhir_ref TEXT,
                status TEXT NOT NULL DEFAULT 'received'
            );

            CREATE TABLE IF NOT EXISTS variant_call (
                id TEXT PRIMARY KEY,
                result_id TEXT NOT NULL REFERENCES screening_result(id) ON DELETE CASCADE,
                gene TEXT NOT NULL,
                hgvs TEXT NOT NULL,
                zygosity TEXT NOT NULL,
                classification TEXT NOT NULL,
                inheritance TEXT NOT NULL,
                encrypted_payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS person_assessment (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                flags TEXT NOT NULL DEFAULT '{}',
                rule_version TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS couple_link (
                id TEXT PRIMARY KEY,
                partner_a TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                partner_b TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS consent_grant (
                id TEXT PRIMARY KEY,
                grantor TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                grantee TEXT NOT NULL,
                scope TEXT NOT NULL,
                purpose TEXT NOT NULL,
                expires_at TEXT,
                revoked_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS couple_result (
                id TEXT PRIMARY KEY,
                couple_link_id TEXT NOT NULL REFERENCES couple_link(id) ON DELETE CASCADE,
                outcome TEXT NOT NULL,
                shared_genes_encrypted TEXT,
                natural_frequency TEXT,
                icon_array_data TEXT,
                rule_version TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS triage_case (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                tier TEXT NOT NULL,
                fired_rules TEXT NOT NULL DEFAULT '[]',
                sla_due TEXT,
                assigned_to TEXT,
                state TEXT NOT NULL DEFAULT 'created',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS referral (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
                service_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'created',
                timestamps_per_state TEXT NOT NULL DEFAULT '{}',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS content_template (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                language TEXT NOT NULL,
                reading_level TEXT NOT NULL,
                body TEXT NOT NULL,
                version TEXT NOT NULL,
                approved_by TEXT NOT NULL DEFAULT 'DRAFT - requires clinical sign-off',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, language, reading_level, version)
            );

            CREATE TABLE IF NOT EXISTS explanation_log (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                template_ids TEXT NOT NULL DEFAULT '[]',
                final_text_hash TEXT NOT NULL,
                raw_content TEXT,
                validator_result TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS comprehension_response (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                quiz_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                score REAL NOT NULL,
                answers TEXT NOT NULL DEFAULT '{}',
                language TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS family_notice (
                id TEXT PRIMARY KEY,
                sender_id_hash TEXT NOT NULL,
                channel TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                condition_name TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                opened BOOLEAN NOT NULL DEFAULT 0,
                booked BOOLEAN NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS values_response (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                answers TEXT NOT NULL,
                share_with_counsellor BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS measure_response (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                measure TEXT NOT NULL,
                phase TEXT NOT NULL,
                score REAL NOT NULL,
                flag BOOLEAN NOT NULL DEFAULT 0,
                items TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_message (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                intents TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reminder (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved BOOLEAN NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS audit_event (
                id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                grant_id TEXT,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS appointment_booking (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
                counsellor_id TEXT NOT NULL,
                slot_time TEXT NOT NULL,
                language_pref TEXT NOT NULL DEFAULT 'ar',
                modality TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'booked',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS service_directory (
                id TEXT PRIMARY KEY,
                name_en TEXT NOT NULL,
                name_ar TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                location TEXT NOT NULL,
                contact_phone TEXT,
                services_offered TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Seed service directory if empty
            cur.execute("SELECT COUNT(*) as cnt FROM service_directory")
            if cur.fetchone()["cnt"] == 0:
                cur.executemany("""
                    INSERT INTO service_directory (id, name_en, name_ar, facility_type, location, contact_phone, services_offered)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    ("serv_skmc", "Demo Hospital A - Medical Genetics (placeholder)", "مستشفى تجريبي أ - قسم الأمراض الجينية (بيانات افتراضية)", "hospital", "Placeholder location", "+971-0-000-0000", "Clinical genetic counselling, confirmatory genomic sequencing, pediatric genetics"),
                    ("serv_ccad", "Demo Hospital B - Genomics Center (placeholder)", "مستشفى تجريبي ب - مركز الجينوم (بيانات افتراضية)", "hospital", "Placeholder location", "+971-0-000-0000", "Adult genetic counselling, pre-conception risk assessment, cardiogenetics"),
                    ("serv_kanad", "Demo Hospital C - Genetic Counselling (placeholder)", "مستشفى تجريبي ج - الإرشاد الجيني (بيانات افتراضية)", "hospital", "Placeholder location", "+971-0-000-0000", "Pre-marital counselling, family cascade testing, maternal-fetal medicine"),
                    ("serv_fakih", "Demo Fertility Centre - PGT-M Lab (placeholder)", "مركز خصوبة تجريبي - مختبر الفحص الجيني للأجنة (بيانات افتراضية)", "fertility_clinic", "Placeholder location", "+971-0-000-0000", "In Vitro Fertilization (IVF), Pre-implantation Genetic Testing for Monogenic diseases (PGT-M)"),
                    ("serv_burjeel", "Demo Hospital D - Fetal Medicine (placeholder)", "مستشفى تجريبي د - طب الجنين (بيانات افتراضية)", "hospital", "Placeholder location", "+971-0-000-0000", "Comprehensive prenatal diagnosis, amniocentesis, fetal anomaly counselling"),
                ])
            conn.commit()
        conn.close()

    # --- RLS Verification Methods ---

    def can_read_person(self, target_person_id: str, current_user_id: str, role: str = "patient") -> bool:
        """RLS check: Person table read access."""
        if role in ("admin", "system", "counsellor"):
            return True
        return target_person_id == current_user_id

    def can_read_screening_result(self, result_id: str, current_user_id: str, role: str = "patient") -> bool:
        """RLS check: Screening result & variants read access."""
        if role in ("admin", "system", "counsellor"):
            return True
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT person_id FROM screening_result WHERE id = ?", (result_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return False
        return row["person_id"] == current_user_id

    def can_read_couple_result(self, couple_link_id: str, current_user_id: str, role: str = "patient") -> bool:
        """RLS check: Couple result read access.
        
        Requires that BOTH partners have an active, unrevoked, unexpired consent grant for 'couple_result'.
        """
        if role == "admin":
            return True

        conn = self.get_connection()
        cur = conn.cursor()

        cur.execute("SELECT partner_a, partner_b, status FROM couple_link WHERE id = ?", (couple_link_id,))
        link = cur.fetchone()
        if not link or link["status"] != "active":
            conn.close()
            return False

        partner_a = link["partner_a"]
        partner_b = link["partner_b"]

        # Current user must be one of the two partners (or counsellor with explicit grant)
        if current_user_id not in (partner_a, partner_b):
            conn.close()
            return False

        # Check Grant from Partner A
        cur.execute("""
            SELECT id FROM consent_grant
            WHERE grantor = ? AND scope = 'couple_result' AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (partner_a,))
        grant_a = cur.fetchone()

        # Check Grant from Partner B
        cur.execute("""
            SELECT id FROM consent_grant
            WHERE grantor = ? AND scope = 'couple_result' AND revoked_at IS NULL
            AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (partner_b,))
        grant_b = cur.fetchone()

        conn.close()
        return bool(grant_a and grant_b)

    def can_read_triage_case(self, case_id: str, current_user_id: str, role: str = "patient") -> bool:
        """RLS check: Triage case access."""
        if role == "admin":
            return True
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT person_id, assigned_to, state FROM triage_case WHERE id = ?", (case_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return False
        if role == "counsellor":
            # Scoped to assigned cases or unassigned open cases in queue, unless closed
            if row["assigned_to"] == current_user_id:
                return True
            if row["state"] in ("created", "offered"):
                return True
            return False
        # Patient can view their own case
        return row["person_id"] == current_user_id


# Global database instance
db = Database()
