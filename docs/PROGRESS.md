# Inherited Disease Risk Platform - Project Progress & Checklist

## Current Status
- **Current Phase**: Phase 0 - Foundations
- **Current Task**: 0.1 Repo skeleton, docker-compose, .env.example, README stub
- **Next Step**: Build Phase 0 deliverables and gate tests

---

## Test & Execution Guide
- **Run Python Engine & Backend Tests**:
  ```powershell
  python -m pytest engine/ backend/ explain/ -v --cov=engine --cov-report=term-missing
  ```
- **Run Hypothesis Symmetry & Engine Property Tests**:
  ```powershell
  python -m pytest engine/tests/test_couple_hypothesis.py -v
  ```
- **Run Linting & Type Checking**:
  ```powershell
  ruff check engine/ backend/ explain/
  mypy engine/ backend/
  ```
- **Start All Services in Docker**:
  ```powershell
  docker compose up -d --build
  ```

---

## Phase Checklist

### Phase 0 - Foundations
- [ ] 0.1 Repo skeleton, `docker-compose.yml`, `.env.example`, `README.md` stub.
- [ ] 0.2 DB schema from PDF data model plus RLS policies and policy test suite.
- [ ] 0.3 Synthetic data generator: 200 people, 80 couples (same-gene, VUS, X-linked male/female, affected, untested partner, minor, pregnant).
- [ ] 0.4 Gene panel metadata file (gene, inheritance mode, condition, severity class; free sources ClinVar/GeneReviews, no OMIM).
- **GATE**: Seeded DB, RLS tests pass. [ ]

### Phase 1 - Engine and Vault
- [ ] 1.1 YAML rule tables (`engine/rules/v1.yaml`) with versioning and clinical sign-off status.
- [ ] 1.2 `classify(person)` and `couple(a, b)` pure deterministic functions with natural-frequency output and icon-array data.
- [ ] 1.3 Engine tests: every individual and couple rule covered, 100% branch coverage on `engine/`, Hypothesis symmetry property test `couple(a, b) == couple(b, a)`.
- [ ] 1.4 Consent grants (grantor, grantee, scope, purpose, expiry, revoked_at), role-based access, revocation hides derived results immediately.
- [ ] 1.5 Hash-chained audit log with tamper-evident `verify_chain()` function and verification tests.
- [ ] 1.6 FastAPI endpoints for individual results, couple matching, consent grants, and audit log inspection.
- **GATE**: Couple result invisible unless BOTH grants active; audit chain verifies; 100% engine coverage. [ ]

### Phase 2 - Explanation and App
- [ ] 2.1 Clinician-approved template library in English and Arabic (MSA/Gulf), simple & standard reading levels, keyed by template ID.
- [ ] 2.2 Explanation pipeline: select -> fill (slots from structured data only, no LLM numbers) -> adapt -> validate -> log.
- [ ] 2.3 Strict validator with tests: number drift, missing disclaimer, banned phrases (directive, stigmatising, deterministic), reading level; fallback verification with bad LLM injection.
- [ ] 2.4 LangGraph flow: explain -> teach-back quiz (3-5 items, fail twice -> counsellor offered) -> triage route.
- [ ] 2.5 User app screens: language & format picker (text, audio, illustrated), layered explanation, icon arrays, RTL Arabic, audio playback (Web Speech/TTS/pre-recorded), persistent "Talk to a person" action.
- **GATE**: User can open result in Arabic, hear it, pass the teach-back quiz. [ ]

### Phase 3 - Triage and Services
- [ ] 3.1 Triage router rules (T0-T3), storing fired rule IDs, never auto-downgrades existing case tier; tests for each rule.
- [ ] 3.2 Multilingual intent classifier (Arabic + English keywords + detector); decision question ("Should we still get married?") triggers fixed non-directive handoff and T2 case.
- [ ] 3.3 Referral state machine: `created` -> `offered` -> `booked` -> `attended` -> (`confirmatory_ordered` -> `confirmatory_resulted`) -> (`specialist_referred` -> `specialist_seen`) -> `closed`.
- [ ] 3.4 Counsellor portal: queue sorted by tier & SLA, rich case packet (result summary, engine output, explanations shown, quiz score, stated preferences), scoped access expiring on case close.
- [ ] 3.5 Internal booking scheduler, case-packet PDF generator (ReportLab), anonymous family notice flow with sender anonymity guarantee.
- **GATE**: Same-gene couple lands in counsellor queue with packet and booking. [ ]

### Phase 4 - Measure and Polish
- [ ] 4.1 Outcomes dashboard: comprehension uplift, counselling uptake, SLA tracking, family reach, privacy events (zero unauthorized reads), equity breakdowns (language, literacy, age band, sex). Explicitly excludes marriage cancellation or single reproductive choices as metrics.
- [ ] 4.2 promptfoo evaluation test suite for LLM safety (directive language, number drift, translation fidelity).
- [ ] 4.3 `docs/DEMO.md` and automated seed script demonstrating Section 12 (Fatima pre-marital screening flow).
- [ ] 4.4 `README.md` with one-command setup, architecture overview, and explicit "Not implemented / Future scope" section.
- **GATE**: Fresh clone runs full demo via `docker compose up` in under 5 minutes. [ ]
