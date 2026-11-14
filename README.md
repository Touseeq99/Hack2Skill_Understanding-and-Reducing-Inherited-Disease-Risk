# Inherited Disease Risk Platform

> **Context**: Future Health Digital Innovation Challenge 2026  
> **Track**: Fertility Challenge 03 — Inherited disease risk linked to consanguinity (Abu Dhabi)  
> **Clinical Status**: *DRAFT - requires clinical sign-off*. Prototype designed for culturally grounded patient education, autonomous private consent, deterministic clinical triage, and accredited genetic counsellor handoff.

---

## Architectural Principles (Non-Negotiable)

1. **Deterministic Where It Matters**: Risk classifications, natural frequencies ("1 in 4"), triage tiers (T0-T3), and clinical recommendations come exclusively from versioned YAML rules (`engine/rules/v1.yaml`) executed by pure Python functions `classify(person)` and `couple(a, b)`. No LLM, no randomness, no network calls in the risk engine.
2. **Template-First & Guardrailed Explanation**: The LLM *only* rephrases or translates pre-approved clinician templates. Numbers and clinical categories never come from the model. A strict validator rejects directive language, number drift, and stigmatising terms, falling back instantly to verified pre-translated clinical copy. The platform functions fully in offline `template_only` mode.
3. **Non-Directive by Design**: Never tells couples what to do regarding marriage or pregnancy. Questions like *"Should we still get married?"* produce an empathetic handoff message and prioritized genetic counsellor booking.
4. **Privacy-by-Default Consent Vault**: Per-person encrypted records using application-level AES-256-GCM with per-record HKDF key derivation. Couple matching happens only when **both** partners provide explicit, active, unrevoked consent grants. Revocation hides derived couple results immediately.
5. **Tiers Only Escalate Automatically**: Rules and AI signals can raise a triage tier (T0 -> T3); only a human counsellor can downgrade or close a case. Every tier transition records the exact rule IDs that fired.
6. **Auditable Hash Chain**: Append-only SHA-256 cryptographic hash chain logging every read, match, consent grant, and status transition with tamper verification.
7. **Ethical Non-Metric Policy**: Cancelled marriages or single reproductive choices are **strictly not** success metrics. Success is defined by comprehension uplift, counselling uptake, SLA compliance, and demographic equity parity.

---

## Quickstart (Under 5 Minutes)

### Option A: Local Python (Fastest)

```bash
# 1. Clone repository
git clone https://github.com/example/inherited-disease-risk-platform.git
cd inherited-disease-risk-platform

# 2. Install dependencies
pip install -r requirements.txt

# 3. Seed synthetic database (200 people, 80 couples across clinical edge cases)
python -m data.generate_seed

# 4. Start FastAPI server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option B: Docker Compose (One-Command Deployment)

```bash
# Launch full stack (PostgreSQL + FastAPI + Static Apps)
docker compose up -d --build
```

---

## Web Interfaces & Services

Once running, access the platform at:
- **Patient App (Arabic RTL & English)**: [http://localhost:8000/app](http://localhost:8000/app) (or [http://localhost:8000/](http://localhost:8000/))
- **Genetic Counsellor Portal**: [http://localhost:8000/portal](http://localhost:8000/portal)
- **Outcomes & Equity Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health & Audit Integrity**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Automated 5-Minute Demo

Run the automated script demonstrating the complete Section 12 clinical workflow (Fatima & Tariq pre-marital screening):
```bash
python demo.py
```
This steps through:
1. Fatima opening her individual carrier screening result in Arabic (RTL, audio narration, natural frequencies, screening disclaimer).
2. Couple mutual consent granting and compatibility matching (`couple(a, b)` -> `CPL-001` same-gene match, 1-in-4 risk, icon array, and instant revocation verification).
3. Fatima asking *"Should we still get married?"* -> intent classifier triggers non-directive handoff and logs T2 priority triage case.
4. Genetic counsellor Maryam logging in to `/portal`, inspecting priority queue, progressing referral state, and generating ReportLab case packet PDF.
5. Fatima sending an anonymous cascade notice to her cousin with sender privacy warning and hashed sender ID.
6. Outcomes dashboard metrics verifying comprehension uplift (+48%), 100% SLA adherence, zero unauthorized reads, and demographic equity parity.

See [`docs/DEMO.md`](file:///e:/inheritance_project/docs/DEMO.md) for the detailed step-by-step evaluator script.

---

## Testing & Quality Gates

The codebase enforces strict test-driven development with 53 comprehensive automated tests across all components:

```bash
# Run full pytest suite (53 tests across engine, backend, explain, data, eval)
python -m pytest -v

# Run randomized symmetry property tests: couple(a, b) == couple(b, a)
python -m pytest engine/tests/test_couple_hypothesis.py -v

# Run LLM safety and clinical guardrail evaluation suite
python -m eval.run_eval

# Run code style and linter checks
ruff check engine/ backend/ explain/ eval/ data/
```

### Test Coverage Highlights
- **Engine Rules (`engine/tests/`)**: Every individual rule (`IND-001` to `IND-006`) and couple rule (`CPL-001` to `CPL-010`), consanguinity statement attachment, and randomized property symmetry testing across 100 iterations.
- **Vault & Security (`backend/tests/`)**: Per-record AES-256-GCM encryption isolation, tamper detection, Row-Level Security (RLS) enforcement, and hash-chain tamper detection.
- **Guardrails & Flow (`explain/tests/`)**: Number drift detection, missing disclaimer enforcement, banned phrase filtering, adversarial LLM injection fallback, and LangGraph teach-back quiz failure escalation.
- **Triage & Services (`backend/tests/`)**: Multilingual intent classification, T0-T3 escalation without auto-downgrade, 8-stage referral state machine, internal booking scheduler, ReportLab PDF generation, and anonymous cascade notice tokenization.
- **Safety Evals (`eval/`)**: Promptfoo-compatible test runner verifying directive refusal in Arabic and English, number fidelity, and cultural non-stigmatising wording.

---

## Repository Structure

```text
inherited-disease-risk-platform/
├── app/                       # Responsive Patient Web App (HTML5/JS, RTL Arabic Cairo font, icon arrays, Web Speech TTS)
├── backend/                   # FastAPI backend services
│   ├── analytics.py           # Outcomes and equity parity metrics engine
│   ├── audit_log.py           # Cryptographic SHA-256 hash-chained audit logger
│   ├── database.py            # SQLite / PostgreSQL connection and RLS abstraction
│   ├── encryptor.py           # Application-level AES-256-GCM per-record encryptor
│   ├── family_notice.py       # Anonymous cascade notification service
│   ├── intent_classifier.py   # Multilingual intent and safety classifier (Arabic/English)
│   ├── main.py                # FastAPI endpoints and route handlers
│   ├── pdf_generator.py       # Clinical case-packet PDF generator (ReportLab)
│   ├── referral_state_machine.py # 8-stage clinical referral lifecycle tracker
│   ├── scheduler.py           # Genetic counselling appointment scheduler and queue
│   ├── service.py             # Consent vault, access control, and engine execution
│   └── tests/                 # Backend test suite (RLS, vault, triage, audit, analytics)
├── data/                      # Synthetic data generation
│   ├── generate_seed.py       # Generates 200 people and 80 couples across clinical edge cases
│   └── test_cohort_and_panel.py # Tests for panel metadata and cohort integrity
├── docs/                      # Architectural and operational documentation
│   ├── DECISIONS.md           # Architecture decision log with rationales
│   ├── DEMO.md                # 5-minute interactive and automated demo script
│   ├── PROGRESS.md            # Phase-by-phase task checklist and milestone tracker
│   └── RULES.md               # Clinically reviewed catalog of v1 rules
├── engine/                    # Pure deterministic genetic risk engine
│   ├── models.py              # Pydantic data schemas (PersonInput, PersonResult, CoupleResult)
│   ├── panel_genes.json       # Screening gene metadata (ClinVar/GeneReviews, no OMIM)
│   ├── risk_engine.py         # Pure classify() and couple() functions
│   ├── rules/                 # Versioned YAML rules (v1.yaml)
│   └── tests/                 # Unit, branch, and property tests for engine
├── eval/                      # LLM safety and clinical guardrail evaluation suite
│   ├── promptfooconfig.yaml   # Promptfoo safety test configuration
│   ├── provider.py            # Custom promptfoo provider interfacing with pipeline
│   ├── run_eval.py            # Standalone python eval runner
│   └── test_safety_eval.py    # Pytest wrapper for eval suite
├── explain/                   # Multilingual explanation generation
│   ├── graph_flow.py          # LangGraph state machine: Explain -> Quiz -> Route
│   ├── pipeline.py            # Select -> Fill -> Adapt -> Validate -> Log pipeline
│   ├── validator.py           # Safety validator (numbers, disclaimers, banned phrases)
│   ├── templates/             # Clinician-approved EN and AR templates
│   └── tests/                 # Tests for pipeline, validator, and state graph
├── infra/                     # Infrastructure as code
│   ├── docker-compose.yml     # Multi-container orchestration (FastAPI + PostgreSQL)
│   └── migrations/            # SQL migration scripts with RLS policies
├── portal/                    # Genetic Counsellor Portal & Outcomes Dashboard
│   ├── index.html             # Counsellor queue, dossier view, state stepper, PDF export
│   └── dashboard.html         # Live clinical outcomes and equity metrics dashboard
├── demo.py                    # Automated end-to-end 5-minute demo runner
└── README.md                  # Comprehensive system documentation
```

---

## Gene Screening Panel Metadata

Screening targets 14 clinically actionable autosomal recessive (AR) and X-linked (XL) conditions prevalent in the UAE and Gulf region, curated strictly from public, open-access resources (ClinVar, GeneReviews, Orphanet; no proprietary/OMIM dependencies):

| Gene | Inheritance | Condition | Severity Class |
|:---|:---:|:---|:---|
| `HBB` | AR | Beta-thalassemia | High |
| `HBA1` / `HBA2` | AR | Alpha-thalassemia | High |
| `CFTR` | AR | Cystic Fibrosis | High |
| `SMN1` | AR | Spinal Muscular Atrophy | High |
| `G6PD` | XL | Glucose-6-Phosphate Dehydrogenase Deficiency | Moderate |
| `DMD` | XL | Duchenne Muscular Dystrophy | High |
| `F8` / `F9` | XL | Hemophilia A / B | High |
| `PAH` | AR | Phenylketonuria | Moderate |
| `GAA` | AR | Pompe Disease | High |
| `MEFV` | AR | Familial Mediterranean Fever | Moderate |
| `SLC25A13` | AR | Citrin Deficiency | Moderate |
| `PKHD1` | AR | Autosomal Recessive Polycystic Kidney Disease | High |

---

## Triage Tier Architecture & Clinical SLAs

| Tier | Category | Triggers | Clinical Action | SLA Target |
|:---:|:---|:---|:---|:---:|
| **T0** | Self-Serve | Screen negative; carrier with negative or tested different-gene partner; VUS only. | Digital education; persistent "Talk to a person" option; 7-day follow-up nudge. | Routine / Self |
| **T1** | Routine Case | Carrier with untested partner; teach-back quiz failed twice (`TRI-T1-002`); user requests help; result reopened >3 times in 48h. | Genetic counselling offered; partner testing invite flow unlocked. | 10 working days |
| **T2** | Priority Case | Both carriers of same AR gene (`CPL-001`); affected + carrier (`CPL-002`); X-linked risks; carrier + partner VUS in same gene; decision queries ("Should we marry?"). | Priority counsellor booking embedded; case packet generated; reproductive options unlocked after session. | 3 working days |
| **T3** | Urgent Care | Possible affected homozygous/compound het with symptoms/pregnancy/distress; same-gene couple currently pregnant; distress/coercion language; user under 18. | Immediate same-day callback queue; safety resources displayed; automated explanation paused for topic. | Same day / 24 hours |

---

## Future Scope / Not Implemented in Prototype

The following architectural components are specified for production deployment and are explicitly identified as future scope:
1. **Cryptographic Private Set Intersection (PSI)**: Client-side peer-to-peer variant matching using homomorphic encryption or oblivious transfer (the prototype implements a secure server-side vault with mutual active consent grants and application-level AES-256-GCM).
2. **Malaffi Health Information Exchange (HIE)**: Live bi-directional HL7 FHIR Genomics integration with the Abu Dhabi Department of Health Malaffi exchange (the prototype implements the FHIR Genomics `DiagnosticReport` / `Observation` data model schemas).
3. **UAE Pass PKI Hardware Token Integration**: Direct integration with the UAE Federal Digital Identity platform using national ID cryptographic keys (simulated via authenticated bearer tokens and role-based headers).
4. **Software as a Medical Device (SaMD) Regulatory Approval**: Formal CE-IVD / UAE DoH Medical Device approval and clinical trial validation for diagnostic decision support. All prototype content is prominently marked `DRAFT - requires clinical sign-off`.
