"""SQLite storage. Swap for PostgreSQL later by keeping this class's method names."""
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, role TEXT NOT NULL, pw_hash TEXT NOT NULL, company TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS candidate_users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL, is_verified INTEGER DEFAULT 0, verified_at REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS interviews(code TEXT PRIMARY KEY, name TEXT, type TEXT, level TEXT, langs TEXT, created_by TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, code TEXT NOT NULL, name TEXT, status TEXT, decision TEXT, joined_at REAL, ended_at REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL, ts REAL, kind TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, candidate_id INTEGER, summary TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, actor TEXT, message TEXT);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        c = self._c()
        c.executescript(SCHEMA)
        try:
            c.execute("ALTER TABLE users ADD COLUMN company TEXT")
        except Exception:
            pass
        c.commit()
        c.close()

    def _c(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _x(self, sql, args=(), fetch=None):
        c = self._c()
        try:
            cur = c.execute(sql, args)
            if fetch == "one":
                r = cur.fetchone()
                out = dict(r) if r else None
            elif fetch == "all":
                out = [dict(r) for r in cur.fetchall()]
            else:
                out = cur.lastrowid
            c.commit()
            return out
        finally:
            c.close()

    # users
    def create_user(self, email, role, pw_hash, company=""):
        return self._x("INSERT INTO users(email,role,pw_hash,company,created_at) VALUES(?,?,?,?,?)", (email.lower(), role, pw_hash, company, time.time()))

    def get_user(self, email):
        return self._x("SELECT * FROM users WHERE email=?", (email.lower(),), "one")

    def list_users(self):
        return self._x("SELECT id,email,role,company,created_at FROM users ORDER BY id", fetch="all")

    def delete_user(self, email):
        self._x("DELETE FROM users WHERE email=?", (email.lower(),))

    # candidate accounts (persistent sign-up & verification)
    def create_candidate_user(self, email, name, pw_hash):
        return self._x("INSERT INTO candidate_users(email,name,pw_hash,is_verified,created_at) VALUES(?,?,?,0,?)",
                       (email.lower(), name, pw_hash, time.time()))

    def get_candidate_user(self, email):
        return self._x("SELECT * FROM candidate_users WHERE email=?", (email.lower(),), "one")

    def get_candidate_user_by_id(self, uid):
        return self._x("SELECT * FROM candidate_users WHERE id=?", (uid,), "one")

    def verify_candidate_user(self, email):
        self._x("UPDATE candidate_users SET is_verified=1, verified_at=? WHERE email=?", (time.time(), email.lower()))
        return self.get_candidate_user(email)

    # interviews
    def create_interview(self, code, name, type_, level, langs, created_by):
        self._x("INSERT INTO interviews VALUES(?,?,?,?,?,?,?)", (code, name, type_, level, json.dumps(langs), created_by, time.time()))

    def get_interview(self, code):
        r = self._x("SELECT * FROM interviews WHERE code=?", (code,), "one")
        if r:
            r["langs"] = json.loads(r["langs"])
        return r

    def list_interviews(self):
        rows = self._x("SELECT * FROM interviews ORDER BY created_at DESC", fetch="all")
        for r in rows:
            r["langs"] = json.loads(r["langs"])
        return rows

    def delete_interview(self, code):
        self._x("DELETE FROM candidates WHERE code=?", (code,))
        self._x("DELETE FROM interviews WHERE code=?", (code,))


    # candidates
    def add_candidate(self, code, name):
        return self._x("INSERT INTO candidates(code,name,status,joined_at) VALUES(?,?,?,?)", (code, name, "waiting", time.time()))

    def get_candidate(self, cid):
        return self._x("SELECT * FROM candidates WHERE id=?", (cid,), "one")

    def list_candidates(self, code):
        return self._x("SELECT * FROM candidates WHERE code=? ORDER BY id", (code,), "all")

    def set_candidate(self, cid, status=None, decision=None):
        if status:
            self._x("UPDATE candidates SET status=? WHERE id=?", (status, cid))
            if status == "done":
                self._x("UPDATE candidates SET ended_at=? WHERE id=?", (time.time(), cid))
        if decision:
            self._x("UPDATE candidates SET decision=? WHERE id=?", (decision, cid))

    # events, records, audit
    def add_event(self, cid, kind, message):
        self._x("INSERT INTO events(candidate_id,ts,kind,message) VALUES(?,?,?,?)", (cid, time.time(), kind, message))

    def list_events(self, cid):
        return self._x("SELECT ts,kind,message FROM events WHERE candidate_id=? ORDER BY id", (cid,), "all")

    def save_record(self, cid):
        cand = self.get_candidate(cid)
        interview = self.get_interview(cand["code"])
        events = self.list_events(cid)
        live = [float(e["message"]) for e in events if e["kind"] == "verdict"]
        summary = {
            "candidate": cand["name"], "interview": interview["name"] if interview else cand["code"],
            "decision": cand["decision"] or "None", "joined_at": cand["joined_at"], "ended_at": cand["ended_at"],
            "liveness_avg": round(sum(live) / len(live), 1) if live else None,
            "liveness_min": min(live) if live else None, "events": events,
        }
        return self._x("INSERT INTO records(candidate_id,summary,created_at) VALUES(?,?,?)", (cid, json.dumps(summary), time.time()))

    def list_records(self):
        rows = self._x("SELECT * FROM records ORDER BY id DESC", fetch="all")
        for r in rows:
            r["summary"] = json.loads(r["summary"])
        return rows

    def delete_record(self, rid):
        self._x("DELETE FROM records WHERE id=?", (rid,))

    def audit(self, actor, message):
        self._x("INSERT INTO audit(ts,actor,message) VALUES(?,?,?)", (time.time(), actor, message))

    def list_audit(self, n=100):
        return self._x("SELECT ts,actor,message FROM audit ORDER BY id DESC LIMIT ?", (n,), "all")

    # privacy: erase a person, and automatic retention (the audit log is kept on purpose)
    def erase_candidate(self, cid):
        self._x("DELETE FROM events WHERE candidate_id=?", (cid,))
        self._x("DELETE FROM records WHERE candidate_id=?", (cid,))
        self._x("DELETE FROM candidates WHERE id=?", (cid,))

    def purge_older_than(self, days):
        if days <= 0:
            return 0
        old = self._x("SELECT id FROM candidates WHERE joined_at<?", (time.time() - days * 86400,), "all")
        for r in old:
            self.erase_candidate(r["id"])
        return len(old)
