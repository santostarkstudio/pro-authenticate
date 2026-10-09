# Project guide for coding agents (read first)

FaceGuard is an interview and test platform that checks a real, live person is on camera. FastAPI backend (`backend/`), a single-page website (`frontend/index.html`), and the owner's own model project that must plug in through `backend/app/verifier/`.

## Commands
- Run: `python scripts/run_local.py` (add `--https` for phones and tablets)
- Before any change is called done: `python scripts/check.py` and `cd backend && python -m unittest discover -s tests -p "test_core.py"` and `pytest`
- Inspect the owner's model project: `python tools/inspect_project.py <folder>`

## Non-negotiable rules
1. **The server decides, the browser only reports.** Never rely on a check that runs only in the page.
2. **Candidate privacy:** candidates never receive verdicts, scores, notes, other candidates' names or ids, and never see each other. Keep `app/rooms.py` rules and their tests passing. Reviewers see "Candidate N" (blind review).
3. **No secrets in frontend files.** Keys and passwords live in `.env` on the server. Never commit `.env`.
4. **Flags are evidence, not verdicts.** Nothing rejects a candidate automatically.
5. Keep the verification result shape: `live` (0-100), `label`, `confidence`, `face`, `b`, `m`, `engine`.
6. Add or update a test for every behaviour you change. Do not claim something works unless a test or a run showed it.
7. Candidate consent text must stay accurate (recording, automatic checks, enlarged video, other candidates never see them).

## Status
- Done: backend (auth, interviews, rooms, verify, records, audit, privacy), website (demo, expanded candidate video, responsive), integration kit, privacy guide.
- Next: (1) connect the owner's model (`docs/INTEGRATION.md`), (2) move the website from browser storage to the API and `/ws/{code}?ticket=`, (3) real video and audio (LiveKit or Jitsi), (4) sandboxed code runner, (5) PostgreSQL, HTTPS, deployment, (6) staff two-factor, signed expiring file links.
- Deferred until the owner asks: optional desktop lockdown mode (for example Safe Exam Browser).

## Where things are
`backend/app/main.py` routes, `rooms.py` live relay and privacy rules, `privacy.py` blind review, `security.py` hashing, tokens and tickets, `db.py` storage, `verifier/` engines. Docs in `docs/` (INTEGRATION, DEVICE_TESTING, PRIVACY).
