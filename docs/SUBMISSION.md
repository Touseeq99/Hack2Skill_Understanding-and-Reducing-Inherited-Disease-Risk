# Understanding and Reducing Inherited Disease Risk: prototype submission

Future Health Digital Innovation Challenge 2026 · Fertility · "Understanding and Reducing Inherited Disease Risk"
Prototype status: working software on **synthetic data only**. Content is a **draft awaiting clinical sign-off**.

## 1. What it is

A private, bilingual (Arabic and English) companion for people and couples who receive pre-marital or preconception
carrier-screening results in Abu Dhabi. It explains the result in plain, non-stigmatising language, lets each person
control exactly what their partner or family can see, routes anything complex or emotionally heavy to a qualified
genetic counsellor, tracks the path to confirmatory testing and specialist services, and measures whether people
understood and could access care. It never tells anyone what to do about a marriage or pregnancy.

Three rules hold everything together:

1. **Deterministic where it matters.** Carrier status, couple risk and triage tiers come from versioned, clinician-reviewable
   rules in plain Python and YAML. No language model touches a number.
2. **Non-directive by construction.** Decision questions ("should we still get married?") get a fixed handoff message and a
   counsellor booking, never an answer. A validator blocks directive, stigmatising and blaming wording.
3. **Privacy is the default.** Nothing is shared with a partner, relative or service without an explicit, revocable, logged
   grant from the data owner.

## 2. Run it

Requirements: Python 3.12 or newer. No database server needed.

```bash
pip install -r requirements.txt
python -m data.generate_seed        # 200 synthetic people, 80 couples, clinical edge cases
python -m data.seed_outcomes        # simulated comprehension cohort for the dashboard
python -m data.seed_cases           # routes the cohort through the real triage router
uvicorn backend.main:app --port 8000
```

| Page | URL |
|---|---|
| Patient app (Arabic RTL and English) | http://localhost:8000/app |
| Counsellor portal | http://localhost:8000/portal |
| Outcomes and equity dashboard | http://localhost:8000/dashboard |
| API documentation | http://localhost:8000/docs |

The pages sign in automatically with a demo one-time code (`123456`). Scripted end-to-end run: `python demo.py`
(about 10 seconds). Full verification: `python -m pytest -q` and `python verify_all.py`.

**Optional ML layer** (safety classifier and approved-library question answering): `pip install -r requirements-ml.txt`, then
`python -m eval.fetch_model` (one-time download of about 220 MB). Without it the app runs on keyword rules only, every chat
reply still offers a human, and free-text education answers are switched off. The demo works in both modes.

## 3. Five-minute demo path

Use the "Demo user" switcher at the top of the patient app (patient or partner).

| Min | What to do | What it shows |
|---|---|---|
| 0:00 | Open the patient app in Arabic; choose the audio format | Carrier result for Fatima, icon array, "screening result, not a diagnosis", layered explanation, teach-back quiz |
| 1:00 | Couple card: click revoke (result disappears), then grant again (it returns) | Joint result appears only while **both** consents are active; revoking hides it for both at once |
| 2:00 | Chat: "Should we still get married?" (then "What does being a carrier mean?") | Fixed non-directive handoff and a T2 case with the rule IDs that fired; the second question gets an approved-library answer |
| 3:00 | Open the counsellor portal; select the case; download the case packet | Queue sorted by tier and SLA, real findings, shared values only if the patient opted in, PDF packet, referral states |
| 4:00 | Back in the app: send an anonymous family notice; open "access history" | Sender is hashed and never disclosed; every read of her data is in a hash-chained log she can see |
| 4:30 | Open the dashboard | Comprehension before and after, uptake, time to referral, equity gaps with n, revocations honoured, "no data yet" where nothing was measured |

## 4. How this maps to the judging criteria

| Criterion | Where the evidence is |
|---|---|
| Health impact and clinical relevance | Section 5 (covers all six challenge requirements); 14-gene panel relevant to the region (thalassaemia, cystic fibrosis, SMA and others); consanguinity handled neutrally with side-by-side figures; counsellor handoff and tracked referrals |
| Technical depth and architecture | Section 6; deterministic engine with property tests, vault encryption, hash-chained audit, FHIR import, embedding-based safety classifier, retrieval over approved content |
| Working solution and demonstration quality | Sections 2, 3, 11: 135 automated tests, a clean-copy install check, a scripted demo, and a dashboard computed from stored data |
| Responsible AI, safety and data governance | Section 7: what AI does and does not do, measured safety results with intervals and caveats, privacy design, deletion, accessibility |
| Scalability and deployment readiness | Section 9: measured single-machine numbers, the known bottlenecks, and a concrete migration plan |
| Commercial viability and path to pilot | Section 10: stakeholders, phases, dependencies and revenue hypotheses (not forecasts) |

## 5. Coverage of the six challenge requirements

| # | Requirement | What the prototype does | Honest gap |
|---|---|---|---|
| 1 | Risk explanation | Carrier, couple and per-pregnancy figures as natural frequencies with icon arrays; one-line summary, what it means, what it does not mean, uncertainty, options; VUS shown as uncertain, never as a number | Arabic and English only; content not yet reviewed by a licensed counsellor |
| 2 | Informed, values-sensitive choices | Seven neutral, equally weighted options (tests enforce no ranking or success claims); detailed options for T2/T3 unlock after counselling; values exercise shared with the counsellor only if the user opts in | Cultural and clinical review of wording still needed |
| 3 | Qualified human counselling | Triage tiers T0 to T3 that can only rise automatically; decision, distress and coercion messages escalate with crisis contacts and an out-of-hours notice; "Talk to a person" always visible | Safety classifier has measurable false alarms and misses (section 7) |
| 4 | Privacy-preserving family workflows | Per-person records, mutual couple consent with instant revocation, anonymous family notice, role-based access, access history for the user, deletion on request | Couple match runs server-side in the vault; private set intersection is future work |
| 5 | Safe linkage to services | Referral state machine from created to closed, booking, case packet PDF, missed-appointment reminder then counsellor outreach, service directory, FHIR bundle import | Booking uses an internal scheduler with static counsellor slots; no real lab or Malaffi connection |
| 6 | Measurable comprehension and access | Pre-check versus post teach-back, decisional conflict and anxiety measures, uptake, time to referral, equity splits by language, literacy, sex and age, all computed from stored data; cancelled marriages are explicitly not a metric | Dashboard uses a simulated cohort; wellbeing measures show "no data yet" until used |

## 6. Architecture

```
 Lab results (FHIR bundle / CSV)         Patient app (AR/EN, RTL)      Counsellor portal      Dashboard
            |                                     |                          |                    |
            +----------------> FastAPI (signed-token auth, role checks) <-----+--------------------+
                                  |
        +-------------------------+----------------------------------------------+
        |                         |                         |                    |
  Consent and privacy vault   Risk engine (pure Python)   Explanation layer     Triage router
  - per-person records        - classify(person)          - approved templates  - rules T0..T3
  - AES-256-GCM payloads      - couple(a, b), symmetric   - validator           - can only escalate
  - grants, revocation        - versioned YAML rules      - approved FAQ        - rule IDs stored
  - hash-chained audit        - no AI, no network         - no generated text   - embedding signals
        |                                                                               |
   SQLite (prototype) -> PostgreSQL + RLS (target)          Referrals, booking, reminders, case packets
```

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic, signed bearer tokens, roles decided on the server |
| Data | SQLite in the prototype; schema and row-level-security policies for PostgreSQL in `infra/migrations/` |
| Engine | Plain Python plus YAML rules (`engine/rules/v1.yaml`), 99% line and branch coverage (engine tests alone), Hypothesis test that `couple(a, b) == couple(b, a)` |
| Encryption | AES-256-GCM with per-record HKDF keys; genes, HGVS names, zygosity and classification exist only inside the encrypted payload |
| Explanation | Approved EN and AR templates, validator for number drift, disclaimers, banned phrases; FAQ retrieval returns approved blocks verbatim |
| Safety classifier | Keyword rules plus multilingual sentence embeddings (ONNX, runs offline) with logistic regression per intent |
| Front end | Single-file HTML/JS pages with a shared accessibility layer; Arabic RTL and English |
| Interop | FHIR R4 Bundle import (`DiagnosticReport` and genomics-style `Observation`) |

## 7. Responsible AI, safety and data governance

### What AI does and does not do
- **Does not:** compute any risk figure, assign any clinical category, choose an option for anyone, or write any text shown to
  users. Generative adapters exist behind a switch but are off by default; the product runs fully without them.
- **Does:** (a) classify a free-text message to decide whether a human should see it (embedding model plus keyword rules);
  (b) pick which approved answer matches a question, or none. Both can only raise attention or show approved text.
- **Hard rules:** AI signals can raise a tier but never lower it; only a counsellor can close or downgrade a case. Every tier
  decision stores the rule IDs that fired; rules that fired on the model alone are marked `~ML`.

### Measured safety performance (frozen held-out set, `docs/SAFETY_EVAL.md`)
| Measure | Keyword rules only | Rules plus embedding model |
|---|---|---|
| Messages with a risk intent flagged (73) | 41% (95% CI 31-53%) | **99%** (95% CI 93-100%) |
| Distress (17) | 24% | 17 of 17 (CI 82-100%) |
| Coercion (18) | 56% | 18 of 18 (CI 82-100%) |
| Benign messages wrongly flagged (30) | 0 of 30 | **7 of 30 = 23%** (CI 12-41%) |

Read these with the caveats: 103 messages written by the development team, Arabic not native-reviewed, and the set was scored
three times (disclosed in the evaluation). The cost of high recall is false alarms: about one harmless message in four is
escalated. A native-speaker held-out set and a pre-agreed release threshold are required before any real use.
Approved-library answers: 58% of valid questions answered correctly (CI 41-74%), no wrong block, 1 of 18 out-of-scope
questions wrongly answered (`docs/RAG_EVAL.md`); the rest fall back to a human.

### Privacy and governance
- Per-person ownership; couples and families are links, not shared records. Couple result requires two active grants and is
  hidden for both the moment either revokes. Revocations are checked by replaying the audit log.
- Variant details are never stored in plaintext columns; the engine receives them decrypted in memory only.
- Append-only, hash-chained audit log with tamper verification; the user can see their own access history.
- Chat text is stored for the assigned counsellor and erased on a deletion request; the audit log keeps intent labels only.
- Right to deletion: `POST /api/users/me/delete` with typed confirmation; a tamper-evident entry records that it happened.
- Notifications carry no result content. LLM requests, when enabled, carry no identifiers.
- Authentication uses signed tokens; the role comes from the account, never from a request header; staff endpoints are
  role-restricted; five failed codes lock an account for five minutes.
- Accessibility: contrast, keyboard operation, dialog focus handling, screen-reader text for icon arrays, text-size control
  (`docs/ACCESSIBILITY.md`); not yet tested with real screen readers.
- Regulatory posture: education and navigation software; clinical decisions stay with licensed counsellors. UAE health-data
  law, the Personal Data Protection Law, Department of Health standards and medical-device classification still need
  confirmation (section 10).

## 8. Assumptions

1. A pre-marital or preconception screening programme already produces variant-level results (gene, HGVS, zygosity, ACMG-style
   class) and can deliver them to the platform, for example through FHIR or Malaffi.
2. Licensed genetic counsellors are available to receive T2 and T3 cases within the proposed SLAs (T3 same day, T2 three
   working days, T1 ten working days); the SLAs are proposals to agree with a clinical partner.
3. The 14-gene panel, rule tables, per-pregnancy figures, the 95% default panel sensitivity and the consanguinity background
   statement (Bennett et al., NSGC 2002) are working values. They must be confirmed by a clinical advisor; the product carries a
   "DRAFT, requires clinical sign-off" status everywhere.
4. Users are 18 or older; a detected minor is escalated and blocked from self-serve.
5. Cousin marriage is treated as a common, valued practice; the product informs choice and never frames it as a fault.
6. Hosting in the UAE and a lawful basis for processing health data will be arranged before real use.

## 9. Scalability and deployment readiness

### Measured (one laptop, one server process, SQLite, no tuning)
| Endpoint | 1 client (median / 95th) | 20 concurrent clients (median / 95th) |
|---|---|---|
| Options library | 5 ms / 5 ms | 32 ms / 34 ms (about 600 req/s) |
| Individual result (decrypt plus engine) | 14 ms / 14 ms | 35 ms / 3.3 s (about 45 req/s) |
| Chat (classifier plus retrieval plus triage plus audit) | 63 ms / 81 ms | 603 ms / 6.3 s (about 13 req/s) |

Under concurrency, writes slow sharply. Causes, found by this test: SQLite allows one writer, every audit event is serialised
by design (hash chain), and the health check re-verified the whole chain on each call (now cached for 30 seconds). These are
prototype limits, not design limits.

### Plan to scale
1. **Database:** port the repository layer to PostgreSQL (the schema and row-level-security policies already exist in
   `infra/migrations/`); connection pooling; read replicas for the dashboard.
2. **Audit chain:** keep one chain per tenant or per day with periodic anchoring, so writes parallelise while tampering stays
   detectable; verify incrementally instead of end to end.
3. **API:** stateless, so it scales horizontally behind a load balancer; move long jobs (PDF packets, reminder sweeps, report
   exports) to a worker queue.
4. **Models:** the embedding model runs on CPU through ONNX in about 20 ms per message; batch or share one instance per worker.
5. **Deployment:** containers, a UAE-hosted environment, secrets in a vault (demo key refused in production mode), monitoring
   and alerting on the audit chain, queue depth and SLA breaches.
6. **Integration:** Malaffi and lab connections through FHIR; UAE Pass for identity in place of the demo one-time code.

### Not yet true
No load test beyond one machine, no Postgres runtime, the Docker path is written but was not run on the build machine, and
there is no monitoring.

## 10. Path to pilot and commercial viability (hypotheses to validate)

**Who benefits and who decides:** couples and individuals (users); genetic counsellors (workload and quality); the Department of
Health and its pre-marital screening programme (population outcomes); labs and hospital groups (follow-through to confirmatory
testing and reproductive-genomics services).

**Pilot path**
1. *Clinical validation (weeks):* a licensed genetic counsellor reviews the rule tables, templates, FAQ blocks, options library
   and consanguinity wording; native Arabic reviewers test the safety classifier on a new held-out set.
2. *Controlled pilot (one clinic, synthetic then consented real users):* counsellors receive T2 and T3 cases; measure
   comprehension, decisional conflict, time to referral and counsellor minutes per case; check equity by language and literacy.
3. *Regulatory and data steps:* confirm medical-device classification, health-data localisation and consent requirements,
   Department of Health approvals, Malaffi and lab integration agreements.
4. *Scale-out:* additional languages for expatriate users (Urdu, Hindi, Tagalog), more clinics, richer reporting.

**Revenue hypotheses (none validated, no figures claimed):** (a) a licence or per-screening fee from the programme owner;
(b) integration and support fees from labs and hospital groups; (c) counsellor-time savings from structured case packets as
the value argument. Cost drivers are counsellor review time, hosting in the UAE, clinical content upkeep and integration work.

**Main risks:** clinical content accuracy; classifier false alarms burdening counsellors; regulatory classification; reliance on
counsellor capacity; cultural acceptance of digital tools for family-sensitive topics.

## 11. Limitations (please read)

- Synthetic data only. No real lab, Malaffi or UAE Pass connection.
- No licensed clinician has reviewed the content; every clinical figure and sentence is a draft. The Arabic is team-written.
- Safety classifier: high recall comes with about 23% false alarms; evaluation set is small and team-written (section 7).
- Dashboard figures come from a simulated cohort and are labelled so; decisional-conflict and anxiety cards read "no data yet"
  until the check-in is used.
- Prototype scale: SQLite, one process, shared demo one-time code. PostgreSQL is a documented target, not a running mode.
- Internal scheduler with static counsellor slots; no calendar or video integration.
- Read-aloud depends on a voice installed on the device (often missing for Arabic); no recorded audio.
- Not tested with real screen readers; axe-core and Lighthouse were not run.
- Only Arabic and English. Generative adapters (Ollama, Gemini) are present but were not exercised in this build.
- Private set intersection for couple matching is not implemented; matching runs inside the server vault.
- The first-load model download (about 220 MB) is required only for the optional ML layer.

## 12. Verification evidence

| Check | Result |
|---|---|
| Automated tests | 135 pass with the ML layer; 127 pass and 8 skip without it |
| Scripted architecture check (`python verify_all.py`) | 50 of 50 |
| Clean-copy install | Copied the working tree into an empty folder, new virtual environment, `pip install -r requirements.txt`, seeded, ran tests, demo and server. This found and fixed a crash (the optional ML library was imported unconditionally), so the install path now works without it |
| Reproducing the ML results from the clean copy | Safety and retrieval evaluations returned the same figures |
| Smoke test of the server from the clean copy | Pages, auth, role checks, options, chat, queue and metrics responded as expected |
| Reproduce the evaluations | `python -m eval.safety_report`, `python -m eval.rag_eval report` |

## 13. Where things are

`engine/` rules and pure functions · `backend/` API, vault, auth, triage, safety, FHIR, reminders · `explain/` templates,
validator, FAQ, options · `eval/` classifiers, held-out sets, accessibility audit · `app/` patient app and shared assets ·
`portal/` counsellor portal and dashboard · `data/` synthetic cohort and seeding · `docs/` evaluations, decisions, rules, guides ·
`infra/` schema and container files.
