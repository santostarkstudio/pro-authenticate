"""Placeholder engine: brightness + frame-to-frame motion. NOT your model."""
import io

import numpy as np
from PIL import Image


def label_for(live: int) -> str:
    return "REAL" if live >= 70 else "BORDERLINE" if live >= 40 else "FAKE"


class DemoVerifier:
    def __init__(self, cap: int = 500):
        self.prev: dict = {}
        self.cap = cap

    def verify(self, image_bytes: bytes, session: str = "default") -> dict:
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((160, 120))
        a = np.asarray(img, dtype=np.float32)
        b = float(a.mean())
        p = self.prev.get(session)
        m = float(np.abs(a - p).mean()) if p is not None else 2.0
        self.prev[session] = a
        if len(self.prev) > self.cap:
            self.prev.pop(next(iter(self.prev)))
        live = 15 if b < 35 else 35 if m < 0.5 else min(95, 55 + m * 10)
        live = int(round(live))
        return {"live": live, "label": label_for(live), "confidence": live / 100, "face": None,
                "b": round(b), "m": round(m, 1), "engine": "demo"}
