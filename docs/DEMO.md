# Inherited Disease Risk Platform - 5-Minute Demo Guide

**Challenge**: Future Health Digital Innovation Challenge 2026  
**Track**: Fertility Challenge 03 — Inherited disease risk linked to consanguinity (Abu Dhabi)  
**Core Principles**: Private by default, culturally grounded, non-stigmatising, and strictly non-directive.

---

## Quick Automated Demo (Single Command)

To run the entire 6-step clinical narrative end-to-end in your terminal:
```bash
python demo.py
```
This executes the exact clinical scenario below in under 10 seconds, verifying all mathematical engines, guardrails, state transitions, and audit chains.

---

## Interactive Browser Demo Walkthrough (5 Minutes)

### Prerequisites
Start the platform locally or via Docker:
```bash
# Option A: Local Python
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Option B: Docker Compose
docker compose up -d --build
```
Open your browser to:
- **Patient App**: [http://localhost:8000/app](http://localhost:8000/app) (or [http://localhost:8000/](http://localhost:8000/))
- **Genetic Counsellor Portal**: [http://localhost:8000/portal](http://localhost:8000/portal)
- **Outcomes & Equity Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Step 1: Fatima Opens Her Carrier Result (Patient App)
**URL**: `http://localhost:8000/app` (Default user: Fatima Al Mansoori, `person_001`)

1. **Native Arabic & RTL**: The app defaults to Arabic (`ar`) with the Cairo typography, fully right-to-left. You can toggle to English at the top right.
2. **Format Picker**: Switch between **Text**, **Audio Narration** (HTML5 Web Speech Synthesis reciting approved clinician phrasing), and **Visual Illustrated** mode.
3. **Core Screening Message**:
   - Status: **Carrier** (`IND-002`, Autosomal Recessive).
   - Gene: `HBB` (Beta-thalassemia).
   - Primary Reassurance: Being a carrier is **not a diagnosis**; carriers are healthy and lead normal lives.
   - Screen Disclaimers: Notice the mandatory header and footer disclaimers (`فحص استكشافي وليس تشخيصاً طبياً`).
4. **Interactive Teach-Back Quiz**:
   - Scroll down to the Teach-Back Quiz.
   - Answer the 3 questions:
     - *Does being a carrier mean you have the disease?* -> Select **No, carriers are healthy**.
     - *When does carrier status matter for future children?* -> Select **Only if my partner carries the same gene**.
     - *Can this screening replace a full diagnostic doctor visit?* -> Select **No, this is a screening tool**.
   - Click **Submit Answers**. Notice your score updates to 100%, and the result is logged to `comprehension_response`.
   - *Adversarial Check*: If a user fails twice, rule `TRI-T1-002` escalates the case and automatically surfaces the "Talk to a Genetic Counsellor" modal.

---

### Step 2: Mutual Couple Consent & Compatibility Matching
**Scenario**: Fatima is engaged to Tariq Al Nuaimi (`person_101`). Both took pre-marital screening.

1. **Mutual Consent Vault**:
   - Navigate to the **Couple Matching** section.
   - Notice the privacy disclaimer: *"Compatibility matching requires mutual, active, unrevoked consent from BOTH partners. 'No shared gene' reveals carrier status regarding screened genes."*
2. **Deterministic Risk Output**:
   - Because Fatima carries `HBB` (c.93-21G>A) and Tariq carries `HBB` (c.118C>T), engine rule `CPL-001` fires (`engine/rules/v1.yaml`).
   - Outcome: **Same Gene Match (Beta-thalassemia)**.
   - Triage Tier: **T2 (Priority)**.
3. **Natural Frequency & Icon Arrays**:
   - Risk is strictly presented as natural frequencies:
     - **1 in 4 (25%)**: Child with Beta-thalassemia major.
     - **1 in 2 (50%)**: Child carrier (healthy like parents).
     - **1 in 4 (25%)**: Child does not inherit the variant.
   - A visual 4-icon grid renders color-coded circles (1 red, 2 amber, 1 green).
4. **Privacy Revocation Test**:
   - If Fatima or Tariq clicks **Revoke Consent**, mutual access is instantly destroyed. Any subsequent call to `/api/couples/cpl_link_001/result` yields an immediate `403 Forbidden` error and logs an audit event.

---

### Step 3: Fatima Asks "Should We Still Get Married?" (Non-Directive Guardrail)
1. **Interactive Conversational Input**:
   - In the "Ask a Question" input box, type:
     ```text
     Should we still get married given our risk?
     ```
     *(Or in Arabic: `هل ننفصل يا دكتور أم نتزوج رغم نتيجة الثلاسيميا؟`)*
2. **Clinical Guardrail Trigger**:
   - The multilingual intent classifier detects a directive decision query (`is_decision_question=True`).
   - The platform **strictly refuses** to give marital advice or pregnancy recommendations.
   - Fixed, pre-approved clinician copy is returned:
     > *"We understand your concerns about marriage and future planning. As a neutral medical platform, we never advise whether or not to marry. Many couples explore options such as Pre-implantation Genetic Testing (PGT-M), prenatal testing, or natural family planning. A priority appointment with a certified genetic counsellor has been booked for you."*
3. **Triage Escalation**:
   - The triage router logs rule `TRI-T2-005` (Decision question handoff) and sets an SLA target of **3 working days**.

---

### Step 4: Genetic Counsellor Portal (`/portal`)
**URL**: `http://localhost:8000/portal` (Login as Counsellor Maryam)

1. **Priority Queue**:
   - View cases organized by clinical tier: **T3 (Urgent / 24h)** -> **T2 (Priority / 3 days)** -> **T1 (Routine / 10 days)**.
   - Notice the live countdown timer displaying SLA due dates.
2. **Clinical Case Packet**:
   - Click on Fatima Al Mansoori's case (`case_...`).
   - Inspect the clinical dossier:
     - Demographics: Age 28, female, Arabic (Gulf).
     - Stated Preferences: Consanguineous relationship (first cousins).
     - Engine Findings: Rule `CPL-001` fired, `HBB` same-gene match.
     - Teach-Back Quiz History: 100% score on post-explanation quiz.
     - Cryptographic Audit Trail: Verification of all consent grants and access events.
3. **Referral State Machine**:
   - Advance the case status using the action stepper:
     - `Created` -> `Offered` -> `Booked` -> `Attended` -> `Confirmatory Ordered` -> `Closed`.
   - Each transition writes an immutable hash-chained audit record.
4. **One-Click Clinical PDF Export**:
   - Click **Download Case Packet PDF**.
   - A ReportLab PDF downloads instantly containing patient identifiers, clinical risk tables, natural frequencies, and the required sign-off footer.

---

### Step 5: Anonymous Family Cascade Notice
**Scenario**: Fatima wishes to inform her extended family (first cousins) that Beta-thalassemia is in the family line, without revealing her identity or clinical diagnosis.

1. **Sender Warning & Consent**:
   - Fatima navigates to the "Inform Family" section.
   - The app displays an explicit privacy notice:
     > *"Privacy Warning: While this message is sent anonymously by the platform and contains no name or test results, relatives may deduce your identity based on who you choose to inform. Your name and test results will NEVER be disclosed."*
2. **Cryptographic Protection**:
   - Fatima enters her cousin's mobile number (`+971501234567`).
   - The system generates an unguessable token (`tok_...`) and stores `sender_id_hash = SHA256(salt + person_001)`. Fatima's actual ID is nowhere in the message.
3. **Recipient Experience**:
   - Relative receives:
     > *"A family relative suggests you consider pre-marital carrier screening for Beta-thalassemia. Confidential booking: https://screen.ad/notice/tok_..."*
   - Opening the link registers an `opened` event in the audit chain and offers free pre-marital screening registration.

---

### Step 6: Outcomes and Equity Parity Dashboard (`/dashboard`)
**URL**: `http://localhost:8000/dashboard`

1. **Explicit Non-Metric Policy Banner**:
   - Highlighted prominently at the top:
     > *"Ethical Policy: Marriage cancellations or single reproductive choices are STRICTLY NOT success metrics. Success is measured by informed decision-making, patient agency, and equitable access."*
2. **Clinical Outcomes**:
   - **Comprehension Uplift**: Pre-explanation baseline: 52.0% -> Post-explanation average: **94.2%** (+42.2 percentage points).
   - **Risk vs Diagnosis Comprehension**: 98.5% correctly distinguish carrier status from illness.
   - **Counselling Uptake**: **66.7%** of T1-T3 high-risk couples attended genetic counselling.
   - **SLA Adherence**: T3 Urgent: 100%, T2 Priority: 97.4%, T1 Routine: 98.8%.
3. **Zero Unauthorized Reads & Privacy Integrity**:
   - Unauthorized access breaches: **0**.
   - Blocked unauthorized attempts: Logged and thwarted by RLS and token verification.
   - Consent revocations honored: **100% instantaneous**.
   - Cryptographic Audit Chain: **VERIFIED OK** (green badge).
4. **Equity Parity Across Demographics**:
   - Language: Arabic (94.5%) vs English (93.8%) — **Gap: 0.7%**.
   - Literacy Preference: Standard (95.1%), Simple (93.4%), Audio (92.8%) — **Gap: 2.3%**.
   - Sex: Female (94.3%) vs Male (94.0%) — **Gap: 0.3%**.
   - Age Band: Minors (92.0%), 18-29 (94.6%), 30+ (93.9%) — **Gap: 2.6%**.
   - **All gaps are well under the 10.0% disparity threshold, achieving full demographic equity parity.**

---

## Seed Data Personas (For Exploration)

| Person ID | Name | Gender | Role / Finding | Target Scenario |
|:---|:---|:---:|:---|:---|
| `person_001` | Fatima Al Mansoori | F | `HBB` Carrier | Canonical pre-marital demo partner |
| `person_101` | Tariq Al Nuaimi | M | `HBB` Carrier | Canonical couple match -> `CPL-001` (T2) |
| `person_002` | Mariam Al Zaabi | F | Pregnant + `HBB` Carrier | Same-gene couple + pregnant -> `TRI-T3-002` (Urgent 24h SLA) |
| `person_003` | Shaikha Al Shamsi | F | Compound Het `HBB` | Possible affected (`IND-005`), non-carrier |
| `person_004` | Reem Al Dhaheri | F | `CFTR` Carrier | Partner untested -> `CPL-007` (T1) |
| `person_005` | Maha Al Suwaidi | F | `DMD` Carrier | X-linked female carrier -> `IND-003` / `CPL-008` (T2) |
| `person_105` | Rashid Al Nuaimi | M | `G6PD` Hemizygous | X-linked affected male -> `IND-004` / `CPL-009` (T2) |
| `person_006` | Noura Al Qubaisi | F | `HBB` Carrier + Partner `HBB` VUS | Uncertain match -> `CPL-006` (T2, no numbers) |
| `person_007` | Hessa Al Falasi | F | `CFTR` Carrier + Partner `HBB` Carrier | Different genes -> `CPL-004` (T0, no shared risk) |
| `person_009` | Khawla Al Marzooqi| F | Panel Negative | Screen negative -> `IND-001` / `CPL-010` (T0) |
| `person_012` | Mira Al Kaabi | F | Age 16 (Minor) | Minor safeguard -> `TRI-T3-005` (Blocks self-serve) |

