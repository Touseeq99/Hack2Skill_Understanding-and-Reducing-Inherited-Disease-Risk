# Enhancement Plan: Gap Analysis vs. Challenge 03 and Architecture PDF

Reviewed 2026-11-18 against `Inherited_Disease_Risk_Solution_Architecture.pdf` (v1.0) and the six challenge requirements.

**How this was checked:** I read the PDF, all docs, the engine, router, validator, pipeline, analytics, `main.py`, and the front-end JS. I ran the test suite in a clean venv: **63 passed**. `verify_all.py` errors on its last check (`K-demo-script`). I did **not** launch the browser UI or Docker, so UI findings come from reading the code.

## 1. Verdict

The back end is strong and matches the PDF's core design: deterministic engine, YAML rules, template-first explanations with a validator, tier-escalation router, hash-chained audit, AES-GCM, a referral state machine and PDF case packets.

Three things would cost points in front of judges:

1. **The patient app is mostly a mock.** `app/index.html` makes only 4 API calls (chat, quiz questions, quiz submit, access history). Consent grant, revoke, couple result, booking and family notice are not wired. "Revoke" and "Confirm booking" are `alert()` calls. The claims "revocation hides the result immediately" and "same-gene couple lands in the counsellor queue" only hold in `demo.py`, not in the UI judges will click.
2. **Some dashboard numbers are made up.** `backend/analytics.py` hard-codes fallbacks and constants: the pre-score baseline of 52.0, "98.5% understand risk vs diagnosis", median referral times, the equity gap of 3.1, `equity_parity_achieved: True`, and fake counts (42 / 31 / 19 notices, 94.2 average score) when tables are empty. Requirement 6 is about *demonstrating measured* outcomes. A judge who asks "where does 52.0 come from?" damages credibility on the whole project.
3. **Requirements 2 and 6 are only partly built.** The options library is static (no tier gating) and there is no values-clarification exercise (PDF section 5), no SURE decisional-conflict or anxiety measure (PDF section 10), and no free-question RAG over approved content.

## 2. Compliance matrix (challenge requirement to status)

| # | Requirement | Status | Evidence and gaps |
|---|---|---|---|
| 1 | Risk explanation (carrier, couple, child risk, uncertainty, risk vs diagnosis) | **Mostly met** | Engine rules IND-001..006 and CPL-001..010, natural frequencies, icon arrays, 8 EN+AR templates, validator. Gaps: result screen is not driven by the API; the consanguinity statement (CNS-001) is not shown in the app; only AR/EN (the PDF names Urdu/Hindi/Tagalog for expats); no LLM adapter has actually been exercised, because the default mode is template-only; reading-level check is just words per sentence. |
| 2 | Informed, values-sensitive, non-coercive choices | **Partial** | The decision-question handoff works. **Partly present:** a static options-library card with neutral options exists in the app (not driven by tier, not API-backed). **Missing:** tier-based release, a values-clarification exercise whose answers can go to the counsellor with permission. (Couple consent was UI-only; now wired, see P0 status.) |
| 3 | Qualified human counselling + clear boundary | **Mostly met** | Non-directive handoff, T0-T3, portal queue and case packet. Gaps: the portal queue shows **hard-coded condition labels by tier** (e.g. any T3 shows "CFTR / Severe Match"); counsellor scoping relies on a self-asserted role header; the intent classifier is regex-only (PDF wants a multilingual classifier plus keywords). |
| 4 | Privacy-preserving family workflows | **Partial** | Strong crypto and audit design. Gaps: **auth is spoofable** (`X-User-Id`/`X-User-Role` headers, defaults to `person_001`, CORS `*` with credentials); `/api/audit/verify` and `/api/analytics/metrics` are open; `/api/family-notice/shareable-card` is **shadowed by `/{token}`** so Option 1 (share personally) cannot be reached; no data-deletion endpoint (PDF: "deletion request removes app data and logs the event"); `/api/triage/evaluate` trusts client-supplied category/pregnancy fields. |
| 5 | Safe, traceable linkage to services | **Partial** | State machine, directory, internal scheduler, PDF packet. Gaps: **never-downgrade is not enforced across calls**: `existing_case_tier` is never loaded, and every `evaluate()` inserts a new case instead of upserting (PDF pseudo-code uses `upsert_case`, so duplicates); no missed-appointment reminder then counsellor outreach (PDF section 7); no FHIR ingestion path (PDF: "results land in the vault first"); booking in the UI is not persisted. |
| 6 | Measurable comprehension and access | **Weak** | Dashboard layout and equity splits are good, but see item 2 in the verdict. Missing: SURE test, anxiety before/after, T3 escalation rate, a real pre/post teach-back (the PDF's pre-check is not stored), a per-group gap check computed from data. |

## 3. Other findings

- **Docs contradict the code.** `DECISIONS.md` DEC-003 says "React/Vite"; the app is single-file HTML. README and `PROGRESS.md` give different test counts (62 / 53; actual 63). README links point to `file:///e:/...`. The README calls graph_flow "LangGraph", but `langgraph` is not a dependency (custom class).
- **Install breaks on a current Python.** `requirements.txt` pins old versions; `psycopg2-binary==2.9.9` failed to build on Python 3.14. A judge running `pip install -r requirements.txt` may fail. Unpinned (no psycopg2) works.
- **`verify_all.py` "50/50" claim is stale**: it currently errors at `K-demo-script` (and crashes printing on a cp1252 console without `PYTHONIOENCODING`).
- **DEC-004 deviates from the PDF** (possible-affected is T2 by default; the PDF says T3). It is documented, but the justification says "the prompt wins over the PDF", which judges will not see. Either follow the PDF, or justify clinically.
- **Accessibility:** zero `aria-*` attributes, no reduced-motion handling, TTS relies on the browser's Arabic voice (the PDF wants pre-recorded fallback for core templates). No speech input.
- **Hard-coded "demo" PII-like data:** recipient number `+971500000000` default in the notice request; fine for synthetic data, but label it.

## 4. Enhancement plan (ordered by score impact)

### P0: Must fix before any demo (about 2 days)
1. **Wire the patient app end to end** to the existing API: load the result from `/api/screening`, couple link, grant, revoke (real call, then re-fetch showing 403 hidden), booking (`/api/portal/.../book` or scheduler), family notice (both options). Add a visible "Demo user" switcher (Fatima / Tariq / cousin / counsellor) instead of spoofable defaults.
2. **Remove every fabricated number** in `analytics.py`. Compute everything from tables; when empty return `null` and "no data yet". Seed `comprehension_response` (pre and post), notices and cases from the synthetic generator so the dashboard is honest, and label it "synthetic cohort". Compute the equity gap and `equity_parity_achieved` from the data.
3. **Triage correctness:** load the existing case for the person, upsert instead of insert, and enforce never-downgrade. Add a test: raise to T3, then re-evaluate a benign signal, and the tier stays T3.
4. **Fix the route-order bug** (`/shareable-card` before `/{token}`) and add a test. Replace hard-coded queue condition labels with the real gene/condition from the case.
5. **Make setup reliable:** loosen or update `requirements.txt` pins, make `psycopg2-binary` optional (extra), and fix `verify_all.py`. Add a one-line "run" command in the README. Fix docs contradictions and the `e:/` links.

### P1: Close the requirement gaps (about 3 to 4 days)
6. **Options library + values clarification (req 2).** Seven neutral, equally weighted cards from a content file (EN/AR), released by tier (detailed T2 options only after counselling). Add a 4 to 6 item "What matters most to you?" exercise whose answers go into the case packet only with an explicit toggle. The validator should enforce equal card length and no ranking.
7. **Real authentication.** Signed session tokens (JWT, or a signed cookie with demo OTP login), role from the token not the header, counsellor access limited to assigned cases and expiring at case close (the PDF says so). Restrict `/api/audit/verify` and analytics, tighten CORS.
8. **Measurement (req 6):** SURE (4 items) after explanation and after counselling; short anxiety check before and after; store the pre-check answers; T3 escalation rate; median time-to-referral from case timestamps; per-group gap with a 10-point threshold flag. Show methods and "synthetic data" on the dashboard.
9. **Safety and recall:** extend the intent classifier (more Gulf-dialect phrasings, pregnancy-plus-couple, self-harm variants), add a recall-focused test set of at least 50 labelled messages (AR and EN), and report recall in the eval. Add an out-of-hours T3 banner with crisis contacts. Check the real local crisis numbers with the clinical advisor.
10. **Service linkage:** missed-appointment reminder followed by counsellor outreach for T2/T3 (scheduler job plus state), referral "closed loop" view for the patient, and a simple FHIR `Observation`/`DiagnosticReport` import endpoint feeding the vault (fits the PDF's "FHIR / CSV for demo").
11. **Data rights:** a deletion-request endpoint that removes app data and logs the event; show it in the privacy screen next to access history.

### P2: Differentiators for the competition (about 3 days)
12. **Languages:** add Urdu (and Hindi or Tagalog if native review is available) for the core 3 templates, flagged "needs native review". This directly supports the "equitable performance across languages" scoring point.
13. **Free-question RAG over approved content only** (PDF section 5). Simple version: embed the template and FAQ library with a multilingual embedding model, return the best approved block or a handoff; run the same validator. Even a keyword/BM25 version works offline.
14. **Local LLM demo:** one working Ollama adapter path with the validator visibly catching a bad output in the demo ("watch it fall back"). Today this exists only in tests.
15. **Accessibility pass:** `aria` roles and labels, keyboard focus, `prefers-reduced-motion`, contrast check, larger-text mode; pre-recorded Arabic audio for the 3 core templates.
16. **Privacy stretch:** a small PSI-style demo (hashed or blinded gene-set intersection) for couple matching, clearly labelled stretch; otherwise keep the honest "server-side vault match" statement.

### P3: Pitch and evidence (about 1 day)
17. Rewrite docs around the *challenge's* six requirements (this matrix), delete "prompt wins over PDF" wording, and state limits honestly (synthetic data, DRAFT clinical sign-off, no SaMD claim).
18. A 5-minute demo that runs **in the browser only**: Fatima in Arabic, then couple consent, then "Should we still get married?", then the counsellor portal, then the anonymous notice, then the dashboard. Record a backup video.
19. A one-slide "what we deliberately do not measure" (marriages cancelled) and a one-slide "limits and next steps" (Malaffi, UAE Pass, DoH approvals, UAE hosting).
20. **Recruit or name a genetic-counsellor advisor** for content review (the PDF calls this the most important credibility hire).

## 5. Suggested order and definition of done

| Day | Work | Done when |
|---|---|---|
| 1 | P0 items 1 to 3 | Clicking through the UI performs real revoke/booking, and a unit test proves never-downgrade |
| 2 | P0 items 4 and 5, P1 item 7 | Fresh `pip install` works; no hard-coded metrics; auth not spoofable |
| 3 to 4 | P1 items 6, 8, 9 | Options library and values exercise visible; dashboard shows SURE and anxiety from data |
| 5 to 6 | P1 items 10 and 11, P2 items 12 to 15 | Reminders, FHIR import, deletion, Urdu, RAG demo, a11y checks pass |
| 7 | P3 | Rehearsed 5-minute demo from a fresh start |

## 6. Questions for the team

- Which deadline are we working to? This plan assumes about 7 working days.
- Is a clinical or genetic-counsellor advisor available to review the content?
- Do we follow the PDF literally for possible-affected (T3), or keep T2 with a clinical justification?

## 7. P0 status (updated 2026-11-18)

| Item | Status | Notes |
|---|---|---|
| 1. Wire patient app | **Done for consent, booking, family cascade, pre-check** | Couple card now reads the real result (403 when a grant is missing), revoke/grant call the API and re-read, booking picks real slots and persists an appointment, family card (share card + anonymous notice) added, pre-check baseline stored. Demo-user switcher added. Still static: the individual result text and layered explanation are not yet loaded from `/api/screening`. |
| 2. Remove fabricated numbers | **Done** | `analytics.py` computes from rows or returns `null`; dashboard renders from the API; `demo.py` prints measured values; the synthetic cohort is simulated by `data/seed_outcomes.py` and labelled as such. Counsellor queue, case view and case-packet PDF no longer contain canned clinical data. |
| 3. Triage upsert + never-downgrade | **Done** | Loads the open case, upserts, merges fired rules, keeps the SLA clock unless the tier rises; tests added. |
| 4. Route-order bug + queue labels | **Done** | `/shareable-card` registered before `/{token}`; unknown case ID returns 404 instead of a canned demo case. |
| 5. Reliable setup | **Done** | Unpinned `requirements.txt` (psycopg2 moved to `requirements-postgres.txt`); `verify_all.py` fixed (50/50); README/DECISIONS/PROGRESS corrected. |

Found and fixed along the way: the shipped demo database had a **forked audit chain** (concurrent writers read the same head hash; verification also ordered by timestamp instead of insertion order), so `/health` reported `audit_chain_valid: false`. Writers are now serialised (`BEGIN IMMEDIATE`), verification uses insertion order, a regression test runs 4 concurrent writers, and the demo DB was re-chained (backup kept outside the repo).

Known leftovers: the demo database still holds ~50 duplicate open cases for `person_001` from earlier runs; some API tests write to the shared demo DB (they should use temp DBs); auth is still header-based (P1 item 7).

## 8. P1 status (updated 2026-11-18)

| Item | Status | Notes |
|---|---|---|
| 6. Options library + values exercise | **Done** | Seven neutral options (`explain/options_library.py`, EN+AR), same structure and closing sentence, tests ban ranking/success claims; detailed options (prenatal, PGT-M, donor, adoption) stay locked for T2/T3 until counselling is attended; values answers are private unless the user opts in, and an opt-out is honoured. Text still needs clinical and cultural review. |
| 7. Real authentication | **Done** | Signed bearer tokens, role decided server-side (patient / counsellor / lab / admin), lockout after 5 failed codes, header identity rejected unless `ALLOW_HEADER_AUTH=1`; portal, analytics and audit-verify are staff-only; CORS no longer allows credentials; `/api/triage/evaluate` derives engine facts on the server. Demo login uses a one-time code (`DEMO_OTP`); production needs UAE Pass. |
| 8. Measurement | **Done (instruments), data is real-only** | SURE (decisional conflict) and a two-item anxiety check, scored on the server, shown on the dashboard with n and pairing. A positive anxiety screen raises a case to T1. Nothing is simulated: the cards read "no data yet" until people use the check-in. T3 escalation rate added. |
| 9. Safety and recall | **Partly done, with a bad finding** | Chat now routes into triage (tier and fired rule IDs shown), crisis contacts and an out-of-hours notice appear for distress or coercion, and chat text no longer goes into the audit log. **But keyword recall on unseen messages is only about 12%** (see `docs/SAFETY_EVAL.md`); the product fails safe (human offer on every reply) and an ML classifier is still needed. |
| 10. Service linkage | **Done** | Missed appointment then a content-free reminder, then counsellor outreach for T2/T3 after 48 h (`/api/admin/run-reminders`, `/api/portal/outreach`); FHIR Bundle import (`/api/fhir/import`, lab or admin only) validates the panel, drops benign calls, encrypts, and refuses duplicates. No scheduler runs the sweep automatically yet. |
| 11. Data rights | **Done** | `POST /api/users/me/delete` (typed confirmation) erases the person's data through cascades and logs the event; the audit entry stays. |

Also fixed along the way:
- **Variant details were stored in plaintext columns** (only a summary string was encrypted), so the "database is not readable" claim was false. Genes, HGVS, zygosity and classification now live only in the AES-GCM payload (`backend/vault.py`); legacy rows are migrated by `python -m data.encrypt_variants` (already run on the demo DB). The demo encryption key is refused when `APP_ENV=production`.
- The counsellor portal showed canned "Explanations Reviewed", "Question Asked" and "Family Notice Sent" rows for every case; they now come from stored data, and the family notice row says it is hidden by design.
- 51 duplicate open cases for `person_001` were merged (`data/consolidate_cases.py`), and `data/seed_cases.py` fills the queue from the real router (47 cases).

Known leftovers after P1: the keyword classifier (above); `/api/screening` and other patient pages are still partly static text; no automatic scheduler for reminders; some API tests still write to the shared demo database; the demo OTP is shared and fixed.


## 9. Safety classifier follow-up (updated 2026-11-18)

Keyword rules caught about 41% of risk messages on a frozen held-out set. An embedding classifier (multilingual MiniLM via
fastembed, offline after a one-time 220 MB download) combined with the rules (OR) catches **99% (95% CI 93-100%)**, with
**23% (CI 12-41%) of benign messages wrongly flagged**. The set is small, written by the team, and was scored three times, so the figures are optimistic; full method, caveats and the
release checklist are in `docs/SAFETY_EVAL.md`. New: `backend/ml_classifier.py`, `eval/train_safety.py`, `eval/safety_report.py`,
`models/safety_clf.json`, `requirements-ml.txt`, `~ML` tags on triage rule IDs, model status in `/health`.

Still needed: native-speaker held-out set and a release threshold; a decision on a lower-confidence tier for model-only coercion;
verified crisis numbers.

## 10. P2 item 13: free-question RAG (updated 2026-11-18)

Done: retrieval over an approved 18-block FAQ library (`explain/faq_library.py`, `backend/rag.py`), verbatim answers only, risk and
decision messages never answered. Held-out: 58% of valid questions answered correctly (CI 41-74%), 0 wrong blocks, 1 of 18 out-of-scope
questions leaked (CI 1-26%). Details and limits in `docs/RAG_EVAL.md`. Also fixed: the chat panel now shows only the rules fired by the
current message (`fired_rules_now`), and a help-request flag no longer blocks an education answer.

Remaining P2: Urdu/Hindi/Tagalog core templates (12), working local-LLM demo with visible validator fallback (14), accessibility pass (15), PSI stretch (16).

## 11. P2 item 15: accessibility pass (updated 2026-11-18)

Done: shared accessibility layer (`app/assets/a11y.css`, `a11y.js`) on all three pages: AA contrast tokens, focus ring, skip link,
dialog semantics with focus trap and Escape, keyboard-operable accordions and queue cards, headings and landmarks, live regions,
text alternatives for icon arrays, text-size control, reduced motion, and honest read-aloud behaviour. A first-party audit script
went from 20 / 50 / 4 findings to 0 on the three pages. **Not run: axe-core, Lighthouse, screen readers, native-speaker review of
the Arabic labels, recorded Arabic audio.** See `docs/ACCESSIBILITY.md`.
