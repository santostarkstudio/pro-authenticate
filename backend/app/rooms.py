"""Live room relay. The SERVER decides who may send what and who receives it.

Privacy rules enforced here:
  * candidates only talk to staff: a candidate's frames, chat and answers never reach another candidate;
  * staff messages reach a candidate only when addressed to that candidate (or are explicit announcements);
  * candidates never receive verdicts, scores, notes, other candidates' names or ids.
A staff "hq" message asks one candidate to send larger frames while the interviewer has the expanded view open.
"""
from dataclasses import dataclass
from typing import Any, Optional

FROM_CANDIDATE = {"frame": "staff", "work": "staff", "hello": "staff", "challenge_done": "staff", "chat": "staff", "signal": "staff"}
FROM_STAFF = {"frame": "candidate", "chat": "candidate", "announce": "candidate", "challenge": "candidate",
              "admit": "candidate", "end": "candidate", "verdict": "staff", "hq": "candidate", "signal": "candidate"}
OPEN_TO_ALL_CANDIDATES = {"frame", "announce"}     # interviewer camera and announcements carry no candidate data


def route(sender_role: str, msg: dict) -> Optional[str]:
    table = FROM_CANDIDATE if sender_role == "candidate" else FROM_STAFF if sender_role == "staff" else {}
    return table.get(msg.get("type"))


@dataclass(eq=False)
class Conn:
    ws: Any
    role: str
    cid: Optional[int] = None
    name: str = ""


def should_deliver(conn: Conn, sender: Conn, target: str, msg: dict) -> bool:
    if conn is sender or conn.role != target:
        return False
    if target == "candidate" and msg.get("type") not in OPEN_TO_ALL_CANDIDATES:
        return conn.cid is not None and msg.get("to") == conn.cid
    return True


def outgoing(recipient: Conn, sender: Conn, msg: dict) -> dict:
    if recipient.role == "candidate":                       # strip every identifier
        out = {k: v for k, v in msg.items() if k not in ("cid", "name", "to")}
        out["from"] = "staff"
        return out
    return {**msg, "from": sender.role, "cid": sender.cid, "name": sender.name}


class Rooms:
    def __init__(self):
        self.rooms: dict = {}

    def add(self, code: str, conn: Conn):
        self.rooms.setdefault(code, []).append(conn)

    def remove(self, code: str, conn: Conn):
        if conn in self.rooms.get(code, []):
            self.rooms[code].remove(conn)

    async def broadcast(self, code: str, sender: Conn, msg: dict):
        target = route(sender.role, msg)
        if target is None:
            return
        for c in list(self.rooms.get(code, [])):
            if should_deliver(c, sender, target, msg):
                try:
                    await c.ws.send_json(outgoing(c, sender, msg))
                except Exception:
                    self.remove(code, c)

    async def push(self, code: str, role: str, msg: dict):
        """Server-originated message (for example admit from a REST call)."""
        for c in list(self.rooms.get(code, [])):
            if c.role == role and (msg.get("to") is None or c.cid == msg["to"]):
                try:
                    await c.ws.send_json(outgoing(c, Conn(None, "staff"), msg) if role == "candidate" else msg)
                except Exception:
                    self.remove(code, c)
