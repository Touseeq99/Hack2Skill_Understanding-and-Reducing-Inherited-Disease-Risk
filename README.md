# Inherited Disease Risk Platform

> **Context**: Future Health Digital Innovation Challenge 2026, Fertility Challenge 03 (Inherited disease risk linked to consanguinity, Abu Dhabi).
> **Clinical Notice**: *DRAFT - requires clinical sign-off*. Prototype designed for patient education, autonomous private consent, deterministic clinical triage, and accredited counsellor handoff.

---

## Architectural Principles
1. **Deterministic Where It Matters**: Risk categories, natural frequency numbers, triage tiers, and recommendations come exclusively from versioned YAML rules executed by pure Python functions (`classify(person)` and `couple(a, b)`).
2. **Template-First & Guardrailed Explanation**: The LLM *only* rephrases or translates pre-approved clinical templates. Numbers and clinical categories never come from the model. Strict validator rejects directive language, number drift, and stigmatising terms, falling back instantly to verified pre-translated clinical copy.
3. **Non-Directive by Design**: Never tells couples what to do regarding marriage or pregnancy. Questions like *"Should we still marry?"* produce an empathetic handoff message and prioritized genetic counsellor booking.
4. **Privacy-by-Default Consent Vault**: Per-person encrypted records. Couple matching happens server-side only when **both** partners provide explicit, revocable consent grants. Revocation hides derived couple results immediately.
5. **Tiers Only Escalate Automatically**: Rules and AI signals can raise a triage tier (T0 -> T3); only a human counsellor can downgrade or close a case.
6. **Auditable Hash Chain**: Append-only cryptographic hash chain logging every read, match, and grant transition.

---

## Quickstart (One Command Demo)

```bash
# Clone the repository
git clone https://github.com/example/inherited-disease-risk-platform.git
cd inherited-disease-risk-platform

# Copy environment settings
cp .env.example .env

# Launch complete platform via Docker Compose
docker compose up -d --build
```

Access the interfaces:
- **FastAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **User Mobile/Web App (Arabic RTL & English)**: [http://localhost:8000/app](http://localhost:8000/app) (or [http://localhost:3000](http://localhost:3000))
- **Genetic Counsellor Portal**: [http://localhost:8000/portal](http://localhost:8000/portal) (or [http://localhost:3001](http://localhost:3001))
- **Outcomes & Analytics Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

---

## Repository Structure

- `docs/`: Architecture document, decision logs, progress tracking, generated clinical rules catalog, and demo walkthrough.
- `engine/`: Pure deterministic Python risk engine and versioned YAML rules (`engine/rules/v1.yaml`).
- `backend/`: FastAPI application, encrypted consent vault, tamper-evident audit chain, and REST endpoints.
- `explain/`: Clinician-approved multilingual templates (Arabic/English), strict validator, and LangGraph workflow.
- `app/`: Patient web & mobile application with RTL Arabic support, accessible icon arrays, and voice narration.
- `portal/`: Genetic counsellor triage management workspace with case packet viewing and ReportLab PDF downloads.
- `data/`: Synthetic dataset generator producing 200 diverse individuals and 80 couples across clinical edge cases.
- `eval/`: Safety regression evaluation suite testing directive language, number drift, and translation fidelity.
- `infra/`: PostgreSQL migrations with Row-Level Security (RLS) policies and Docker configuration.

---

## Testing

```bash
# Run all unit, integration, and property tests
python -m pytest -v --cov=engine --cov-report=term-missing

# Run Hypothesis symmetry property tests
python -m pytest engine/tests/test_couple_hypothesis.py -v
```

---

## Future Scope / Not Implemented in Prototype
- Cryptographic Private Set Intersection (PSI) protocol between client devices (server-side vault matching used in prototype).
- Direct bi-directional integration with Malaffi (Abu Dhabi Health Information Exchange).
- Real UAE Pass PKI hardware token authentication (simulated via bearer token / mock user context).
- Medical device CE-IVD / UAE DoH Software as a Medical Device (SaMD) regulatory approval.
