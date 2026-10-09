# FaceGuard — interview platform with live identity verification

Two views in one product: candidates join with a code, staff run and review the session. Verification comes from your Python model through one small contract (`backend/app/verifier/base.py`).

```
faceguard/
├─ backend/            FastAPI: auth, interviews, live rooms (WebSocket), verification, records, audit
│  ├─ app/verifier/    demo.py (placeholder)  model_adapter.py (YOUR MODEL goes here)
│  └─ tests/           test_core.py (runs now)  test_api.py (needs requirements)
├─ frontend/           index.html (the website you approved) + config.js
├─ deploy/             nginx configs: one port for candidates, one for staff
├─ docs/prototypes/    earlier website versions (camera fixes, tour, records tabs)
└─ docker-compose.yml  backend :8000, candidates :8081, staff :8082
```

## Run it (no Docker)
```
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env                              # then edit the secret and admin password
python -m unittest discover -s tests -p "test_core.py"  # quick checks
pytest                                                  # full API checks
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000. Staff sign in: the email and password from `.env` (default `hr@company.com` / `demo`: change it).
The page now sends every camera frame to `POST /api/verify`, so the verdict comes from the backend. `GET /api/health` shows which engine answered.

## Two ports, one backend
`docker compose up --build` gives candidates `http://localhost:8081` and staff `http://localhost:8082`. Ports are only convenience: **security comes from roles.** The server issues staff or candidate tokens, rejects staff routes for candidates, and the live room (`app/rooms.py`) never sends verdicts, scores or notes to a candidate. In production use two domains instead, for example `join.yourcompany.com` and `staff.yourcompany.com`.

## Connect your model (the next 30 minutes)
1. Copy your trained files into `backend/models/` (YOLO face weights and the Keras classifier).
2. Open `backend/app/verifier/model_adapter.py` and fill the three TODOs: input size, REAL class index, preprocessing. They must match your training code.
3. `pip install ultralytics tensorflow`, set `FG_VERIFIER=model` in `.env`, restart.
4. Check `GET /api/health` shows `ModelVerifier`, then open the site: the verdict chip now uses your model.
The result shape is fixed: `live` 0–100, `label`, `confidence`, `face`. Keep it and the website needs no change.

## What works today
- Backend: staff login, owner-managed accounts, interviews with codes, candidate join, admit / reject / end, stored session records, audit log, rate-limited `/api/verify`, authenticated WebSocket rooms.
- Website: the approved interface, using the backend for verification.
- Tests: security, database, demo verifier and room-isolation rules pass (`test_core.py`). The HTTP and WebSocket tests are written but have not been run in the build environment.

## Roadmap
| Step | Work | Done when |
|---|---|---|
| 1 (done) | Backend, contract, tests, folders | `/api/verify` answers the website |
| 2 | Move the website's data from browser storage to the API and `/ws/{code}` | Two different computers can run an interview |
| 3 | Real video and audio between people (LiveKit or Jitsi) | Candidate and interviewer hear and see each other |
| 4 | Code runner in a sandbox (Judge0 or Piston) | Python, Java, C++ and SQL run on the server |
| 5 | PostgreSQL, file storage for evidence frames, HTTPS, deployment | A candidate in another city completes an interview |
| 6 | Identity match against the reference photo, random challenges checked by the model | Impostor and replay tests are flagged |

## Security checklist before real users
- Replace `FG_SECRET` and the admin password. Keep `.env` out of git (`.gitignore` does this).
- **Revoke any API key you pasted into a chat or committed to a repository**, and keep keys on the server only.
- Require a token on `/api/verify` for real deployments (the frontend change is small).
- Tell candidates about recording and automatic checks, keep retention short, and get legal advice (India's DPDP Act, 2023).
- A flag is evidence, not a verdict. A person decides.

## Expanded candidate video (interviewer)
Click the candidate video in the console to open a large inspection view: zoom and pan, brightness and contrast, mirror, freeze, compare with the reference, save evidence, send a challenge, switch candidate with the arrow keys, and real full screen.
While it is open the interviewer's page sends `{type:"hq", to:<candidate id>, on:true}`. The server relays it **only to that candidate**, whose browser then adds a larger JPEG (`hq`) to its normal frame messages. Closing sends `on:false`. Candidates cannot send `hq`, and opening the view, freezing and saving evidence are written to the event log (and the audit log when done through the API).
Later, with the real video call, this view simply shows the full-resolution video track.

## Easy model integration and device testing
- Share your project folder with the assistant. `docs/INTEGRATION.md` lists what to include.
- Or try it yourself: `python tools/inspect_project.py <your folder>` reports what it found and writes a draft `models/model.json`.
- `FG_VERIFIER=custom` plus `FG_CUSTOM=module:function` reuses a function from your own project without rewriting it.
- `./run.sh` or `run.bat` starts everything. Add `--https` for phones and tablets (`docs/DEVICE_TESTING.md`).
- `python scripts/check.py` is the before-you-deploy checklist.

## Candidate privacy
Candidates never see each other, never receive scores or staff data, and are erased on request or after the retention period. See `docs/PRIVACY.md` for the table of who sees what and the honest limits. Live connections now use single-use tickets: call `POST /api/ws-ticket` with the sign-in token, then connect to `/ws/{code}?ticket=...`.
