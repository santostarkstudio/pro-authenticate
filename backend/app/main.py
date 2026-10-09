import json
import secrets
import time
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, settings as default_settings
from .db import DB
from .privacy import mask_candidate, mask_record
from .rooms import Conn, Rooms
from .security import Tickets, hash_password, make_token, read_token, verify_password
from .verifier import decode_data_url, get_verifier

LANGS = ["JavaScript", "Python", "Java", "C++", "SQL"]
MAX_WS_BYTES = 400_000


class Limiter:
    """Tiny per-client rate limit: `limit` calls per `window` seconds."""
    def __init__(self, limit=20, window=1.0):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def ok(self, key: str) -> bool:
        now, q = time.time(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class LoginIn(BaseModel):
    email: str
    password: str


class StaffRegisterIn(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=6)


class CandidateRegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=6)


class CandidateLoginIn(BaseModel):
    email: str
    password: str


class CandidateVerifyIn(BaseModel):
    image: Optional[str] = None


class InterviewIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(Technical|Non-Technical)$")
    level: str = Field(default="Standard", pattern="^(Basic|Standard|Hard)$")
    langs: List[str] = ["JavaScript"]


class JoinIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class StatusIn(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(waiting|admitted|rejected|done)$")
    decision: Optional[str] = Field(default=None, pattern="^(Shortlisted|Hold|Rejected)$")


class EventIn(BaseModel):
    kind: str = "note"
    message: str = Field(max_length=500)


class UserIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    role: str = Field(default="Interviewer", pattern="^(Owner|Interviewer|Reviewer)$")


class VerifyIn(BaseModel):
    image: str
    session: str = ""


class AIQuestionIn(BaseModel):
    role: str = "Software Engineer"
    type: str = "Coding"
    level: str = "Standard"


class AIEvaluateIn(BaseModel):
    code: str
    language: str = "JavaScript"
    problem: str = "firstUnique character"


def create_app(cfg: Settings = default_settings, db: DB = None, verifier=None) -> FastAPI:
    db = db or DB(cfg.db_path)
    verifier = verifier or get_verifier(cfg)
    rooms, limiter, tickets, join_limit = Rooms(), Limiter(), Tickets(), Limiter(120, 60)
    if not db.get_user(cfg.admin_email):
        db.create_user(cfg.admin_email, "Owner", hash_password(cfg.admin_password))
    if not db.get_interview("DX8LLW"):
        db.create_interview("DX8LLW", "Software Engineer · Verification Demo", "Coding", "Standard", ["JavaScript", "Python"], cfg.admin_email)
    if not db.get_interview("DEMO01"):
        db.create_interview("DEMO01", "General Assessment · Demo", "Non-coding", "Standard", ["JavaScript"], cfg.admin_email)
    if not db.get_interview("KPTKMD"):
        db.create_interview("KPTKMD", "Technical Interview · Live Session", "Coding", "Standard", ["JavaScript", "Python"], cfg.admin_email)

    db.purge_older_than(cfg.retention_days)
    app = FastAPI(title="PRO-AUTHENTICATOR API")
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors.split(","), allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def safe_headers(request: Request, call_next):
        r = await call_next(request)
        r.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                          "Permissions-Policy": "camera=(self), microphone=(self)"})
        if request.url.path.startswith(("/api", "/ws")):
            r.headers["Cache-Control"] = "no-store"          # candidate data must not sit in caches
        return r

    def claims(authorization: Optional[str] = Header(None)) -> dict:
        token = (authorization or "").removeprefix("Bearer ").strip()
        c = read_token(cfg.secret, token)
        if not c:
            raise HTTPException(401, "Sign in required")
        return c

    def staff(c: dict = Depends(claims)) -> dict:
        if c["role"] != "staff":
            raise HTTPException(403, "Staff only")
        return c

    def owner(c: dict = Depends(staff)) -> dict:
        if c.get("title") != "Owner":
            raise HTTPException(403, "Owner only")
        return c

    @app.get("/api/health")
    def health():
        return {"ok": True, "engine": type(verifier).__name__, "mode": cfg.verifier, "ai": bool(os.environ.get("GEMINI_API_KEY"))}

    # ---- AI powered by Gemini 3.8 Flash
    @app.post("/api/ai/questions")
    async def ai_questions(body: AIQuestionIn):
        from .ai import generate_questions
        try:
            qs = await generate_questions(body.role, body.type, body.level)
            return {"questions": qs}
        except Exception as e:
            return {"questions": [
                "Explain how you design scalable and secure distributed services.",
                "Describe a challenging bug you debugged and your step-by-step resolution.",
                "How do you ensure zero-trust security and data privacy in production applications?"
            ], "fallback": True, "error": str(e)}

    @app.post("/api/ai/evaluate")
    async def ai_eval(body: AIEvaluateIn):
        from .ai import evaluate_code
        try:
            return await evaluate_code(body.code, body.language, body.problem)
        except Exception as e:
            return {"feedback": f"Evaluation note: {str(e)}"}

    # ---- auth and staff accounts
    @app.post("/api/auth/register-staff", status_code=201)
    def register_staff(body: StaffRegisterIn):
        if db.get_user(body.email):
            raise HTTPException(409, "An account with this email already exists")
        db.create_user(body.email, "Owner", hash_password(body.password), company=body.company)
        db.audit(body.email, f"New company registered: {body.company}")
        token = make_token(cfg.secret, body.email, "staff", cfg.token_hours, title="Owner", company=body.company)
        return {"token": token, "title": "Owner", "company": body.company}

    @app.post("/api/auth/login")
    def login(body: LoginIn):
        u = db.get_user(body.email)
        if not u or not verify_password(body.password, u["pw_hash"]):
            db.audit(body.email, "Failed sign-in")
            raise HTTPException(401, "Wrong email or password")
        db.audit(u["email"], "Signed in")
        company = u.get("company") or ""
        return {"token": make_token(cfg.secret, u["email"], "staff", cfg.token_hours, title=u["role"], company=company), "title": u["role"], "company": company}

    # ---- candidate accounts: signup, login, profile verification
    @app.post("/api/candidate-auth/register", status_code=201)
    def register_candidate(body: CandidateRegisterIn):
        if db.get_candidate_user(body.email):
            raise HTTPException(409, "A candidate account with this email already exists")
        db.create_candidate_user(body.email, body.name, hash_password(body.password))
        token = make_token(cfg.secret, body.email, "candidate_user", 24, name=body.name, is_verified=False)
        return {"token": token, "email": body.email, "name": body.name, "is_verified": False}

    @app.post("/api/candidate-auth/login")
    def login_candidate(body: CandidateLoginIn):
        u = db.get_candidate_user(body.email)
        if not u or not verify_password(body.password, u["pw_hash"]):
            raise HTTPException(401, "Wrong email or password")
        is_verified = bool(u.get("is_verified"))
        token = make_token(cfg.secret, u["email"], "candidate_user", 24, name=u["name"], is_verified=is_verified)
        return {"token": token, "email": u["email"], "name": u["name"], "is_verified": is_verified}

    @app.post("/api/candidate-auth/verify")
    def verify_candidate(body: CandidateVerifyIn, c: dict = Depends(claims)):
        if c.get("role") != "candidate_user":
            raise HTTPException(403, "Candidate account required")
        u = db.verify_candidate_user(c["sub"])
        token = make_token(cfg.secret, u["email"], "candidate_user", 24, name=u["name"], is_verified=True)
        return {"ok": True, "token": token, "is_verified": True}

    @app.get("/api/candidate-auth/me")
    def get_candidate_me(c: dict = Depends(claims)):
        if c.get("role") != "candidate_user":
            raise HTTPException(403, "Candidate account required")
        u = db.get_candidate_user(c["sub"])
        if not u:
            raise HTTPException(404, "Candidate not found")
        return {"email": u["email"], "name": u["name"], "is_verified": bool(u.get("is_verified"))}

    @app.get("/api/users")
    def users(_: dict = Depends(owner)):
        return db.list_users()

    @app.post("/api/users", status_code=201)
    def add_user(body: UserIn, c: dict = Depends(owner)):
        if db.get_user(body.email):
            raise HTTPException(409, "Email already exists")
        db.create_user(body.email, body.role, hash_password(body.password))
        db.audit(c["sub"], f"Account added: {body.email}")
        return {"ok": True}

    @app.delete("/api/users/{email}")
    def del_user(email: str, c: dict = Depends(owner)):
        if email.lower() == c["sub"].lower():
            raise HTTPException(400, "You cannot remove yourself")
        db.delete_user(email)
        db.audit(c["sub"], f"Account removed: {email}")
        return {"ok": True}

    # ---- interviews
    @app.post("/api/interviews", status_code=201)
    def create_interview(body: InterviewIn, c: dict = Depends(staff)):
        langs = [x for x in body.langs if x in LANGS] or ["JavaScript"]
        code = secrets.token_hex(5).upper()
        db.create_interview(code, body.name, body.type, body.level, langs, c["sub"])
        db.audit(c["sub"], f"Interview created: {code}")
        return db.get_interview(code)

    @app.get("/api/interviews")
    def list_interviews(_: dict = Depends(staff)):
        return db.list_interviews()

    @app.delete("/api/interviews/{code}", status_code=204)
    def delete_interview(code: str, c: dict = Depends(staff)):
        code = code.upper()
        if not db.get_interview(code):
            raise HTTPException(404, "Interview not found")
        db.delete_interview(code)
        db.audit(c["sub"], f"Interview deleted: {code}")

    @app.get("/api/interviews/{code}")
    def public_interview(code: str, request: Request):
        if not join_limit.ok("p" + (request.client.host if request.client else "x")):
            raise HTTPException(429, "Too many attempts")
        i = db.get_interview(code.upper())
        if not i:
            raise HTTPException(404, "Code not found")
        return {"code": i["code"], "name": i["name"], "type": i["type"], "langs": i["langs"]}

    @app.post("/api/interviews/{code}/join")
    def join(code: str, body: JoinIn, request: Request):
        if not join_limit.ok("j" + (request.client.host if request.client else "x")):
            raise HTTPException(429, "Too many attempts")
        code = code.upper()
        if not db.get_interview(code):
            raise HTTPException(404, "Code not found")
        cid = db.add_candidate(code, body.name)
        db.add_event(cid, "join", "Joined waiting room")
        return {"candidate_id": cid, "token": make_token(cfg.secret, f"c{cid}", "candidate", 4, cid=cid, code=code, name=body.name)}

    @app.get("/api/interviews/{code}/candidates")
    def candidates(code: str, c: dict = Depends(staff)):
        return [mask_candidate(r, c.get("title")) for r in db.list_candidates(code.upper())]

    @app.post("/api/candidates/{cid}/status")
    async def set_status(cid: int, body: StatusIn, c: dict = Depends(staff)):
        cand = db.get_candidate(cid)
        if not cand:
            raise HTTPException(404, "Candidate not found")
        db.set_candidate(cid, body.status, body.decision)
        if body.status:
            db.add_event(cid, "status", f"Status: {body.status}")
        if body.decision:
            db.add_event(cid, "decision", f"Decision: {body.decision}")
        if body.status == "done":
            db.save_record(cid)
        db.audit(c["sub"], f"Candidate {cid}: {body.status or ''} {body.decision or ''}".strip())
        # Map REST status values to the WebSocket event types the frontend expects.
        # The rooms routing table and handleWS() both use "admit" (not "admitted") and "end" (not "rejected").
        ws_type_map = {"admitted": "admit", "rejected": "end", "done": "end"}
        ws_type = ws_type_map.get(body.status, body.status) if body.status else "decision"
        await rooms.push(cand["code"], "candidate", {"type": ws_type, "to": cid})
        return db.get_candidate(cid)

    @app.post("/api/candidates/{cid}/events", status_code=201)
    def add_event(cid: int, body: EventIn, c: dict = Depends(claims)):
        if c["role"] == "candidate" and c.get("cid") != cid:
            raise HTTPException(403, "Not your session")
        db.add_event(cid, body.kind, body.message)
        if c["role"] == "staff":
            db.audit(c["sub"], f"Candidate {cid}: {body.kind} - {body.message}")
        return {"ok": True}

    @app.get("/api/candidates/{cid}/events")
    def events(cid: int, _: dict = Depends(staff)):
        return db.list_events(cid)

    # ---- stored sessions and audit
    @app.get("/api/records")
    def records(c: dict = Depends(staff)):
        return [mask_record(r, c.get("title")) for r in db.list_records()]

    @app.delete("/api/records/{rid}")
    def del_record(rid: int, c: dict = Depends(owner)):
        db.delete_record(rid)
        db.audit(c["sub"], f"Record deleted: {rid}")
        return {"ok": True}

    @app.get("/api/audit")
    def audit(_: dict = Depends(staff)):
        return db.list_audit()

    # ---- verification (the call your frontend's analyze() makes)
    @app.post("/api/verify")
    def verify(body: VerifyIn, request: Request):
        key = request.client.host if request.client else "x"
        if not limiter.ok(key):
            raise HTTPException(429, "Too many frames")
        try:
            data = decode_data_url(body.image)
            return verifier.verify(data, body.session or key)
        except Exception:
            raise HTTPException(422, "Could not read image")

    # ---- privacy: erase one person completely (the audit log keeps only that an erasure happened)
    @app.delete("/api/candidates/{cid}")
    def erase(cid: int, c: dict = Depends(owner)):
        if not db.get_candidate(cid):
            raise HTTPException(404, "Candidate not found")
        db.erase_candidate(cid)
        db.audit(c["sub"], f"Candidate {cid} erased")
        return {"ok": True}

    @app.post("/api/ws-ticket")
    def ws_ticket(c: dict = Depends(claims)):
        return {"ticket": tickets.issue(c)}

    # ---- live room
    @app.websocket("/ws/{code}")
    async def ws(websocket: WebSocket, code: str, ticket: str = ""):
        code = code.upper()
        c = tickets.redeem(ticket)
        if not c or not db.get_interview(code) or (c["role"] == "candidate" and c.get("code") != code):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        conn = Conn(websocket, c["role"], c.get("cid"), c.get("name", c["sub"]))
        rooms.add(code, conn)
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw) > MAX_WS_BYTES:
                    continue                      # oversized message: ignore
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    await rooms.broadcast(code, conn, msg)
        except WebSocketDisconnect:
            pass
        finally:
            rooms.remove(code, conn)

    import os
    if os.path.isdir(cfg.frontend_dir):
        app.mount("/", StaticFiles(directory=cfg.frontend_dir, html=True), name="frontend")
    return app


app = create_app()
