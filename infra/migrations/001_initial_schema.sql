-- 001_initial_schema.sql
-- Inherited Disease Risk Platform Database Schema with Row-Level Security (RLS)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Person
CREATE TABLE IF NOT EXISTS person (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    auth_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'ar',
    literacy_pref TEXT NOT NULL DEFAULT 'standard',
    dob_year INTEGER NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('F', 'M')),
    pregnancy_status BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Screening Result
CREATE TABLE IF NOT EXISTS screening_result (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    panel_id TEXT NOT NULL,
    lab_id TEXT NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    fhir_ref TEXT,
    status TEXT NOT NULL DEFAULT 'received'
);

-- 3. Variant Call (Encrypted Payload)
CREATE TABLE IF NOT EXISTS variant_call (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    result_id TEXT NOT NULL REFERENCES screening_result(id) ON DELETE CASCADE,
    gene TEXT NOT NULL,
    hgvs TEXT NOT NULL,
    zygosity TEXT NOT NULL CHECK (zygosity IN ('heterozygous', 'homozygous', 'hemizygous')),
    classification TEXT NOT NULL CHECK (classification IN ('pathogenic', 'likely_pathogenic', 'VUS', 'benign', 'likely_benign')),
    inheritance TEXT NOT NULL CHECK (inheritance IN ('AR', 'XL')),
    encrypted_payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Person Assessment (Deterministic Engine Output)
CREATE TABLE IF NOT EXISTS person_assessment (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('screen_negative', 'carrier', 'xlinked_carrier', 'xlinked_male', 'possible_affected', 'uncertain')),
    flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    rule_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Couple Link
CREATE TABLE IF NOT EXISTS couple_link (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    partner_a TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    partner_b TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'revoked')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_different_partners CHECK (partner_a != partner_b)
);

-- 6. Consent Grant
CREATE TABLE IF NOT EXISTS consent_grant (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    grantor TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    grantee TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('couple_result', 'share_summary', 'counsellor_case', 'research_aggregate')),
    purpose TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Couple Result
CREATE TABLE IF NOT EXISTS couple_result (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    couple_link_id TEXT NOT NULL REFERENCES couple_link(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL CHECK (outcome IN ('same_gene_match', 'no_shared_gene', 'uncertain_match', 'incomplete', 'xlinked_risk')),
    shared_genes_encrypted TEXT,
    natural_frequency TEXT,
    icon_array_data JSONB,
    rule_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Triage Case
CREATE TABLE IF NOT EXISTS triage_case (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('T0', 'T1', 'T2', 'T3')),
    fired_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    sla_due TIMESTAMP WITH TIME ZONE,
    assigned_to TEXT,
    state TEXT NOT NULL DEFAULT 'created' CHECK (state IN ('created', 'offered', 'booked', 'attended', 'closed', 'downgraded_by_counsellor')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Referral
CREATE TABLE IF NOT EXISTS referral (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
    service_id TEXT NOT NULL CHECK (service_id IN ('counselling', 'confirmatory_lab', 'pgt_m', 'prenatal')),
    state TEXT NOT NULL DEFAULT 'created' CHECK (state IN ('created', 'offered', 'booked', 'attended', 'confirmatory_ordered', 'confirmatory_resulted', 'specialist_referred', 'specialist_seen', 'closed')),
    timestamps_per_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. Content Template
CREATE TABLE IF NOT EXISTS content_template (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    key TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('ar', 'en')),
    reading_level TEXT NOT NULL CHECK (reading_level IN ('simple', 'standard')),
    body TEXT NOT NULL,
    version TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT 'DRAFT - requires clinical sign-off',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_template_key_lang_level UNIQUE (key, language, reading_level, version)
);

-- 11. Explanation Log
CREATE TABLE IF NOT EXISTS explanation_log (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    template_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_text_hash TEXT NOT NULL,
    raw_content TEXT,
    validator_result JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. Comprehension Response
CREATE TABLE IF NOT EXISTS comprehension_response (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    quiz_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('pre', 'post')),
    score NUMERIC(5,2) NOT NULL,
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    language TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 13. Family Notice
CREATE TABLE IF NOT EXISTS family_notice (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    sender_id_hash TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('sms', 'whatsapp', 'email')),
    token TEXT UNIQUE NOT NULL,
    condition_name TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    opened BOOLEAN NOT NULL DEFAULT FALSE,
    booked BOOLEAN NOT NULL DEFAULT FALSE
);

-- 14. Audit Event (Hash-Chained)
CREATE TABLE IF NOT EXISTS audit_event (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    grant_id TEXT,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 15. Booking Appointment (Internal Scheduler)
CREATE TABLE IF NOT EXISTS appointment_booking (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
    counsellor_id TEXT NOT NULL,
    slot_time TIMESTAMP WITH TIME ZONE NOT NULL,
    language_pref TEXT NOT NULL DEFAULT 'ar',
    modality TEXT NOT NULL CHECK (modality IN ('video', 'in_person')),
    status TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'attended', 'rescheduled', 'cancelled', 'no_show')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

--------------------------------------------------------------------------------
-- ROW-LEVEL SECURITY (RLS) POLICIES
--------------------------------------------------------------------------------

ALTER TABLE person ENABLE ROW LEVEL SECURITY;
ALTER TABLE screening_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE variant_call ENABLE ROW LEVEL SECURITY;
ALTER TABLE person_assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE couple_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_grant ENABLE ROW LEVEL SECURITY;
ALTER TABLE triage_case ENABLE ROW LEVEL SECURITY;

-- Helper session parameter functions
-- current_setting('app.current_user_id', true)
-- current_setting('app.current_role', true)

-- Person Policy
CREATE POLICY person_owner_policy ON person
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR id = current_setting('app.current_user_id', true)
    );

-- Screening Result Policy
CREATE POLICY screening_owner_policy ON screening_result
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR person_id = current_setting('app.current_user_id', true)
    );

-- Variant Call Policy (owner only)
CREATE POLICY variant_owner_policy ON variant_call
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR result_id IN (
            SELECT id FROM screening_result WHERE person_id = current_setting('app.current_user_id', true)
        )
    );

-- Person Assessment Policy (owner only)
CREATE POLICY assessment_owner_policy ON person_assessment
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR person_id = current_setting('app.current_user_id', true)
    );

-- Consent Grant Policy (grantor and grantee can see)
CREATE POLICY grant_access_policy ON consent_grant
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR grantor = current_setting('app.current_user_id', true)
        OR (grantee = current_setting('app.current_user_id', true) AND revoked_at IS NULL)
    );

-- Couple Result Policy: ONLY VISIBLE IF BOTH ACTIVE GRANTS EXIST
CREATE POLICY couple_read_policy ON couple_result
    FOR SELECT
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR (
            EXISTS (
                SELECT 1 FROM couple_link cl
                WHERE cl.id = couple_result.couple_link_id
                AND (cl.partner_a = current_setting('app.current_user_id', true) OR cl.partner_b = current_setting('app.current_user_id', true))
                AND cl.status = 'active'
                AND EXISTS (
                    SELECT 1 FROM consent_grant g1
                    WHERE g1.grantor = cl.partner_a
                    AND g1.scope = 'couple_result'
                    AND g1.revoked_at IS NULL
                    AND (g1.expires_at IS NULL OR g1.expires_at > CURRENT_TIMESTAMP)
                )
                AND EXISTS (
                    SELECT 1 FROM consent_grant g2
                    WHERE g2.grantor = cl.partner_b
                    AND g2.scope = 'couple_result'
                    AND g2.revoked_at IS NULL
                    AND (g2.expires_at IS NULL OR g2.expires_at > CURRENT_TIMESTAMP)
                )
            )
        )
    );

-- Triage Case Policy (owner or assigned counsellor or admin)
CREATE POLICY triage_case_access_policy ON triage_case
    FOR ALL
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR person_id = current_setting('app.current_user_id', true)
        OR (
            current_setting('app.current_role', true) = 'counsellor'
            AND (assigned_to = current_setting('app.current_user_id', true) OR state = 'created' OR state = 'offered')
        )
    );

-- Accredited Service Directory Table
CREATE TABLE IF NOT EXISTS service_directory (
    id TEXT PRIMARY KEY,
    name_en TEXT NOT NULL,
    name_ar TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    location TEXT NOT NULL,
    contact_phone TEXT,
    services_offered TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO service_directory (id, name_en, name_ar, facility_type, location, contact_phone, services_offered)
VALUES 
    ('serv_skmc', 'Demo Hospital A - Medical Genetics (placeholder)', 'مستشفى تجريبي أ - قسم الأمراض الجينية (بيانات افتراضية)', 'hospital', 'Placeholder location', '+971-0-000-0000', 'Clinical genetic counselling, confirmatory genomic sequencing, pediatric genetics'),
    ('serv_ccad', 'Demo Hospital B - Genomics Center (placeholder)', 'مستشفى تجريبي ب - مركز الجينوم (بيانات افتراضية)', 'hospital', 'Placeholder location', '+971-0-000-0000', 'Adult genetic counselling, pre-conception risk assessment, cardiogenetics'),
    ('serv_kanad', 'Demo Hospital C - Genetic Counselling (placeholder)', 'مستشفى تجريبي ج - الإرشاد الجيني (بيانات افتراضية)', 'hospital', 'Placeholder location', '+971-0-000-0000', 'Pre-marital counselling, family cascade testing, maternal-fetal medicine'),
    ('serv_fakih', 'Demo Fertility Centre - PGT-M Lab (placeholder)', 'مركز خصوبة تجريبي - مختبر الفحص الجيني للأجنة (بيانات افتراضية)', 'fertility_clinic', 'Placeholder location', '+971-0-000-0000', 'In Vitro Fertilization (IVF), Pre-implantation Genetic Testing for Monogenic diseases (PGT-M)'),
    ('serv_burjeel', 'Demo Hospital D - Fetal Medicine (placeholder)', 'مستشفى تجريبي د - طب الجنين (بيانات افتراضية)', 'hospital', 'Placeholder location', '+971-0-000-0000', 'Comprehensive prenatal diagnosis, amniocentesis, fetal anomaly counselling')
ON CONFLICT (id) DO NOTHING;



-- Values clarification answers (shared with the counsellor only when share_with_counsellor is true)
CREATE TABLE IF NOT EXISTS values_response (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    answers JSONB NOT NULL,
    share_with_counsellor BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- SURE (decisional conflict) and anxiety (GAD-2) measures, scored server-side
CREATE TABLE IF NOT EXISTS measure_response (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    measure TEXT NOT NULL CHECK (measure IN ('sure', 'anxiety')),
    phase TEXT NOT NULL,
    score REAL NOT NULL,
    flag BOOLEAN NOT NULL DEFAULT FALSE,
    items JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- Questions the user asked the assistant (shown to the assigned counsellor; erased on deletion request)
CREATE TABLE IF NOT EXISTS chat_message (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    intents JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- Missed-appointment reminders (content-free) and counsellor outreach tasks
CREATE TABLE IF NOT EXISTS reminder (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES triage_case(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('gentle_reminder', 'counsellor_outreach')),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE
);
