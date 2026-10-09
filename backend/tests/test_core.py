"""Runs with the standard library plus Pillow and numpy:  python -m unittest discover -s tests"""
import asyncio
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image  # noqa: E402

from app.db import DB  # noqa: E402
from app.rooms import Conn, Rooms, route, should_deliver  # noqa: E402
from app.privacy import mask_candidate, mask_record  # noqa: E402
from app.security import Tickets, hash_password, make_token, read_token, verify_password  # noqa: E402
from app.verifier import decode_data_url  # noqa: E402
from app.verifier.demo import DemoVerifier  # noqa: E402


def jpg(color, noise=0):
    import random
    img = Image.new("RGB", (160, 120), color)
    if noise:
        px = img.load()
        for _ in range(noise):
            px[random.randrange(160), random.randrange(120)] = (255, 255, 255)
    b = io.BytesIO()
    img.save(b, "JPEG")
    return b.getvalue()


class SecurityTests(unittest.TestCase):
    def test_password(self):
        h = hash_password("secret1")
        self.assertTrue(verify_password("secret1", h))
        self.assertFalse(verify_password("nope", h))
        self.assertFalse(verify_password("x", "garbage"))

    def test_token(self):
        t = make_token("k", "a@b.c", "staff", title="Owner")
        self.assertEqual(read_token("k", t)["title"], "Owner")
        self.assertIsNone(read_token("other", t))
        self.assertIsNone(read_token("k", "bad"))


class DbTests(unittest.TestCase):
    def test_flow_and_record(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(os.path.join(d, "t.db"))
            db.create_user("A@x.com", "Owner", "h")
            self.assertEqual(db.get_user("a@x.com")["role"], "Owner")
            db.create_interview("ABC123", "Intern", "Coding", "Standard", ["Python"], "a@x.com")
            self.assertEqual(db.get_interview("ABC123")["langs"], ["Python"])
            cid = db.add_candidate("ABC123", "Sam")
            db.add_event(cid, "verdict", "90")
            db.add_event(cid, "verdict", "50")
            db.set_candidate(cid, status="done", decision="Hold")
            db.save_record(cid)
            rec = db.list_records()[0]["summary"]
            self.assertEqual(rec["liveness_avg"], 70.0)
            self.assertEqual(rec["liveness_min"], 50.0)
            self.assertEqual(rec["decision"], "Hold")


class VerifierTests(unittest.TestCase):
    def test_dark_is_low(self):
        v = DemoVerifier()
        self.assertEqual(v.verify(jpg((5, 5, 5)), "s")["label"], "FAKE")

    def test_static_flagged_moving_live(self):
        v = DemoVerifier()
        a = jpg((120, 120, 120))
        v.verify(a, "s")
        self.assertLess(v.verify(a, "s")["live"], 40)          # still image
        v2 = DemoVerifier()
        v2.verify(jpg((120, 120, 120), noise=50), "s")
        self.assertGreaterEqual(v2.verify(jpg((120, 120, 120), noise=3000), "s")["live"], 40)

    def test_decode(self):
        import base64
        raw = jpg((9, 9, 9))
        self.assertEqual(decode_data_url("data:image/jpeg;base64," + base64.b64encode(raw).decode()), raw)
        with self.assertRaises(Exception):
            decode_data_url("")


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, m):
        self.sent.append(m)


class RoomTests(unittest.TestCase):
    def test_routing_rules(self):
        self.assertEqual(route("candidate", {"type": "frame"}), "staff")
        self.assertIsNone(route("candidate", {"type": "verdict"}))      # candidates cannot send verdicts
        self.assertIsNone(route("candidate", {"type": "challenge"}))
        self.assertEqual(route("staff", {"type": "challenge"}), "candidate")
        self.assertIsNone(route("guest", {"type": "chat"}))

    def test_candidate_never_receives_staff_data(self):
        async def run():
            r = Rooms()
            st, cd, cd2 = Conn(FakeWS(), "staff"), Conn(FakeWS(), "candidate", 1), Conn(FakeWS(), "candidate", 2)
            for c in (st, cd, cd2):
                r.add("X", c)
            await r.broadcast("X", st, {"type": "verdict", "live": 12})
            await r.broadcast("X", st, {"type": "challenge", "text": "blink", "to": 1})
            await r.broadcast("X", cd, {"type": "frame", "img": "x"})
            self.assertEqual([m["type"] for m in cd.ws.sent], ["challenge"])
            self.assertNotIn("cid", cd.ws.sent[0])
            self.assertEqual(cd2.ws.sent, [])
            self.assertEqual([m["type"] for m in st.ws.sent], ["frame"])
        asyncio.run(run())

    def test_expanded_view_request(self):
        self.assertEqual(route("staff", {"type": "hq"}), "candidate")
        self.assertIsNone(route("candidate", {"type": "hq"}))     # a candidate cannot ask for staff features

        async def run():
            r = Rooms()
            st, a, b = Conn(FakeWS(), "staff"), Conn(FakeWS(), "candidate", 1), Conn(FakeWS(), "candidate", 2)
            for c in (st, a, b):
                r.add("X", c)
            await r.broadcast("X", st, {"type": "hq", "on": True, "to": 2})
            self.assertEqual(a.ws.sent, [])
            self.assertEqual(b.ws.sent[0]["type"], "hq")
        asyncio.run(run())


class PrivacyTests(unittest.TestCase):
    def test_candidates_never_see_each_other(self):
        async def run():
            r = Rooms()
            st, a, b = Conn(FakeWS(), "staff", name="Ravi"), Conn(FakeWS(), "candidate", 1, "Asha"), Conn(FakeWS(), "candidate", 2, "Ben")
            for c in (st, a, b):
                r.add("X", c)
            await r.broadcast("X", a, {"type": "chat", "text": "hello"})           # candidate chat goes to staff only
            await r.broadcast("X", a, {"type": "work", "txt": "my answer"})
            self.assertEqual(b.ws.sent, [])
            self.assertEqual([m["type"] for m in st.ws.sent], ["chat", "work"])
            self.assertEqual(st.ws.sent[0]["name"], "Asha")                          # staff may see who wrote it
            await r.broadcast("X", st, {"type": "chat", "text": "private", "to": 2})
            await r.broadcast("X", st, {"type": "chat", "text": "no address"})        # unaddressed staff chat reaches nobody
            await r.broadcast("X", st, {"type": "announce", "text": "5 minutes"})
            self.assertEqual([m["type"] for m in a.ws.sent], ["announce"])
            self.assertEqual([m["type"] for m in b.ws.sent], ["chat", "announce"])
            for m in a.ws.sent + b.ws.sent:
                self.assertTrue(set(m) <= {"type", "text", "from"})                  # no names or ids ever
        asyncio.run(run())

    def test_ticket_single_use_and_expiry(self):
        t = Tickets(ttl=30)
        k = t.issue({"role": "staff"})
        self.assertEqual(t.redeem(k), {"role": "staff"})
        self.assertIsNone(t.redeem(k))
        self.assertIsNone(Tickets(ttl=-1).redeem(Tickets(ttl=-1).issue({})))
        self.assertIsNone(t.redeem("guess"))

    def test_blind_review(self):
        row = {"id": 7, "name": "Asha Rao"}
        self.assertEqual(mask_candidate(row, "Reviewer")["name"], "Candidate 7")
        self.assertEqual(mask_candidate(row, "Interviewer")["name"], "Asha Rao")
        rec = {"candidate_id": 7, "summary": {"candidate": "Asha Rao", "events": []}}
        self.assertEqual(mask_record(rec, "Reviewer")["summary"]["candidate"], "Candidate 7")
        self.assertEqual(rec["summary"]["candidate"], "Asha Rao")                    # original untouched

    def test_erase_and_retention(self):
        with tempfile.TemporaryDirectory() as d:
            db = DB(os.path.join(d, "t.db"))
            db.create_interview("ABC", "I", "Coding", "Standard", ["Python"], "x")
            a, b = db.add_candidate("ABC", "Asha"), db.add_candidate("ABC", "Ben")
            db.add_event(a, "note", "x")
            db.set_candidate(a, status="done")
            db.save_record(a)
            db.erase_candidate(a)
            self.assertIsNone(db.get_candidate(a))
            self.assertEqual(db.list_events(a), [])
            self.assertEqual(db.list_records(), [])
            self.assertIsNotNone(db.get_candidate(b))
            self.assertEqual(db.purge_older_than(0), 0)
            db._x("UPDATE candidates SET joined_at=1 WHERE id=?", (b,))
            self.assertEqual(db.purge_older_than(30), 1)
            self.assertIsNone(db.get_candidate(b))


class IntegrationTests(unittest.TestCase):
    def test_normalize_many_shapes(self):
        from app.verifier.custom import normalize
        self.assertEqual(normalize(("REAL", 0.93))["live"], 93)
        self.assertEqual(normalize(("FAKE", 0.9))["live"], 10)
        self.assertEqual(normalize({"label": "spoof", "confidence": 88})["live"], 12)
        self.assertEqual(normalize(0.5)["label"], "BORDERLINE")
        self.assertEqual(normalize("NO_FACE")["label"], "NO_FACE")
        self.assertEqual(normalize({"label": "REAL", "confidence": 0.9, "faces": 0})["label"], "NO_FACE")
        with self.assertRaises(ValueError):
            normalize(object())

    def test_custom_function_in_a_project_folder(self):
        from app.verifier.custom import CustomVerifier
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "my_pipeline.py"), "w").write(
                "def predict_frame(frame):\n    return ('REAL', 0.9) if frame[0, 0, 0] > frame[0, 0, 2] else ('FAKE', 0.8)\n")
            try:
                v = CustomVerifier("my_pipeline:predict_frame", d, bgr=False)
                self.assertEqual(v.verify(jpg((200, 10, 10)))["label"], "REAL")     # frame arrives as RGB when bgr=False
                self.assertEqual(v.verify(jpg((10, 10, 200)))["label"], "FAKE")
                v2 = CustomVerifier("my_pipeline:predict_frame", d, bgr=True)       # OpenCV order: channels flipped
                self.assertEqual(v2.verify(jpg((200, 10, 10)))["label"], "FAKE")
            finally:
                os.chdir(old)

    def test_model_helpers(self):
        import numpy as np
        from app.verifier.model_adapter import prepare, real_probability
        self.assertAlmostEqual(real_probability(np.array([[0.2, 0.8]]), 1), 0.8)
        self.assertAlmostEqual(real_probability(np.array([[0.7]]), 1), 0.7)
        self.assertAlmostEqual(real_probability(np.array([[0.7]]), 0), 0.3)
        self.assertEqual(prepare(np.full((2, 2, 3), 255), "div255").max(), 1.0)
        self.assertEqual(prepare(np.zeros((4, 4, 3)), "none").shape, (1, 4, 4, 3))

    def test_inspector_reads_a_project(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
        from inspect_project import analyse
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "detect.py"), "w").write(
                "from ultralytics import YOLO\nfrom tensorflow.keras.models import load_model\nclass_names = ['fake', 'real']\n"
                "m = load_model('liveness.h5')\nimg = cv2.resize(face, (160, 160)) / 255.0\ndef predict_frame(frame):\n    return m.predict(img)\n")
            open(os.path.join(d, "yolo_face.pt"), "wb").write(b"x")
            open(os.path.join(d, "liveness.h5"), "wb").write(b"x")
            r = analyse(d)
            self.assertEqual(r["guess"]["input_size"], [160, 160])
            self.assertEqual(r["guess"]["real_index"], 1)
            self.assertEqual(r["guess"]["preprocess"], "div255")
            self.assertEqual(r["candidate_functions"][0]["function"], "predict_frame")
            self.assertTrue(r["guess"]["yolo_path"].endswith("yolo_face.pt"))


if __name__ == "__main__":
    unittest.main()
