# Team guide: deploy, demo, and what not to break

For teammates who received the zip. About 10 minutes to be running. Synthetic data only; content is a draft awaiting clinical sign-off.

## 1. What is in the package

| Item | What it is |
|---|---|
| `inheritance-platform-handoff.zip` | The whole project (code, tests, docs, trained safety weights). About 1.5 MB. **This is all you need to run the demo.** |
| `docs/SUBMISSION.pdf` | The technical document we submit (also `docs/SUBMISSION.md`) |
| `docs/TEAM_GUIDE.md` | This file |

## 2. Start it (Windows)

1. Install **Python 3.12 or newer** from python.org. Tick "Add python.exe to PATH".
2. Unzip the project to a folder without spaces if you can (for example `C:\inheritance_project`).
3. Double-click **`run_demo.bat`** (or run it in a terminal). The first run creates a virtual environment, installs the packages, creates the synthetic database and starts the server. This takes a few minutes the first time and seconds afterwards.
4. Your browser opens the patient app. Stop the server with Ctrl+C in its window.

macOS / Linux: `chmod +x run_demo.sh && ./run_demo.sh`.

Useful options: `run_demo.bat reset` (wipe and re-seed the demo data), `run_demo.bat setup` (install only), `run_demo.bat ml` (add the ML layer).

| Page | URL |
|---|---|
| Patient app (Arabic and English) | http://127.0.0.1:8000/app |
| Counsellor portal | http://127.0.0.1:8000/portal |
| Outcomes and equity dashboard | http://127.0.0.1:8000/dashboard |
| API documentation | http://127.0.0.1:8000/docs |

**Sign-in:** none needed. The pages sign in automatically with the demo one-time code `123456` (the patient app has a "Demo user" switcher for patient and partner).

## 3. The optional ML layer (safety classifier and free-question answers)

Without it the demo works: keyword rules protect, and chat replies offer a human, but the assistant will not answer education questions from the library.

With it: run `run_demo.bat ml`. It installs the libraries and downloads the embedding model once (about 250 MB, from Hugging Face) into `modelsastembed`. After that it works offline. To avoid several downloads, one teammate can copy their whole `modelsastembed` folder to the others (USB or shared drive); it is not in the zip because it is large and contains duplicate links. Check `http://127.0.0.1:8000/health`: `"embedding_model": true` means it is active.

## 4. Run the 5-minute demo

Follow `docs/SUBMISSION.md`, section 3. In short: Arabic result with audio and quiz, then revoke and grant couple consent, then ask "Should we still get married?" and "What does being a carrier mean?" in the chat, then open the counsellor portal and download the case packet, send an anonymous family notice and open access history, then show the dashboard.

Before every demo or recording: `run_demo.bat reset` so everyone sees the same clean state (the demo couple Fatima and Tariq starts with consent active and a T2 case).

Say at the start: **prototype, synthetic data, draft awaiting clinical sign-off.**

## 5. Check that everything works

```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python verify_all.py
.venv\Scripts\python demo.py
```
Expected: about 127 tests pass (135 with the ML layer; 8 skipped without it), `verify_all.py` prints 50 passed, `demo.py` ends with "ALL 6 DEMO STEPS COMPLETED".

## 6. Putting it on a server (optional, do this only if the organisers need a link)

1. Docker: `docker compose up -d --build` builds one container with the API and the demo data on port 8000. **This path was written but not run yet**; test it before relying on it.
2. A plain VM or cloud service: copy the project, then run `run_demo.sh setup` and start `uvicorn backend.main:app --host 0.0.0.0 --port 8000` behind a reverse proxy with HTTPS.
3. Change `AUTH_SECRET` and `DEMO_OTP` for anything shared on the internet. Publishing is a decision for the whole team: the app holds synthetic data only, but the demo code is public in the docs.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| "Python not found" | Install Python 3.12+ and tick "Add to PATH"; open a new terminal |
| Port 8000 in use | Close the other server, or start with `.venv\Scripts\python -m uvicorn backend.main:app --port 8001` |
| Empty queue or empty dashboard | `run_demo.bat reset` |
| Chat never answers a question | ML layer not active (see section 3); handoff messages are expected |
| Strange state after clicking around | `run_demo.bat reset` |
| Pip install fails on `psycopg2` | Not needed; use `requirements.txt` only (Postgres is not a supported runtime) |

## 8. Ground rules

- Do not describe it as clinically validated, certified, or deployed. It is a prototype.
- Quote the safety numbers with their caveats (`docs/SAFETY_EVAL.md`): 99% of risk messages flagged, 23% of harmless messages also flagged, small team-written test set.
- Never put real patient data in it.
- The submission lists what we do not have: no clinician review, no real lab or Malaffi link, no screen-reader testing. Keep to that.
