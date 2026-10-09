"""Needs the full requirements:  pip install -r requirements.txt && pytest"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import DB  # noqa: E402
from app.main import create_app  # noqa: E402


def client():
    d = tempfile.mkdtemp()
    cfg = Settings(secret="t", db_path=os.path.join(d, "t.db"), admin_email="a@x.com", admin_password="pass123", frontend_dir="/nonexistent")
    return TestClient(create_app(cfg, DB(cfg.db_path)))


def test_full_flow():
    c = client()
    assert c.post("/api/auth/login", json={"email": "a@x.com", "password": "bad"}).status_code == 401
    tok = c.post("/api/auth/login", json={"email": "a@x.com", "password": "pass123"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    iv = c.post("/api/interviews", json={"name": "Intern", "type": "Coding", "langs": ["Python"]}, headers=h).json()
    assert c.get("/api/interviews").status_code == 401
    j = c.post(f"/api/interviews/{iv['code']}/join", json={"name": "Sam"}).json()
    ch = {"Authorization": f"Bearer {j['token']}"}
    assert c.get("/api/records", headers=ch).status_code == 403          # candidate cannot open staff data
    c.post(f"/api/candidates/{j['candidate_id']}/status", json={"status": "done", "decision": "Hold"}, headers=h)
    assert len(c.get("/api/records", headers=h).json()) == 1


def test_room_isolation():
    c = client()
    tok = c.post("/api/auth/login", json={"email": "a@x.com", "password": "pass123"}).json()["token"]
    code = c.post("/api/interviews", json={"name": "I", "type": "Coding"}, headers={"Authorization": f"Bearer {tok}"}).json()["code"]
    ct = c.post(f"/api/interviews/{code}/join", json={"name": "Sam"}).json()["token"]
    def ticket(token):
        return c.post("/api/ws-ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]

    ts, tc = ticket(tok), ticket(ct)
    with c.websocket_connect(f"/ws/{code}?ticket={ts}") as staff, c.websocket_connect(f"/ws/{code}?ticket={tc}") as cand:
        cid = c.get(f"/api/interviews/{code}/candidates", headers={"Authorization": f"Bearer {tok}"}).json()[0]["id"]
        staff.send_json({"type": "verdict", "live": 10})
        staff.send_json({"type": "chat", "text": "hi", "to": cid})
        got = cand.receive_json()
        assert got["type"] == "chat" and "cid" not in got and "name" not in got   # the verdict never reached the candidate
