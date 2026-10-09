"""Zero-rewrite integration: point FG_CUSTOM at a function that already lives in YOUR project.

    FG_VERIFIER=custom
    FG_CUSTOM=my_pipeline:predict_frame        # module:function, found inside backend/model_project/

The function receives one video frame as a numpy array (H, W, 3, uint8; BGR by default like OpenCV)
and may return any of:
    ("REAL", 0.93)  |  ("FAKE", 0.88)  |  {"label": "REAL", "confidence": 0.93, "faces": 1}  |  0.93 (chance it is real)  |  "REAL"
"""
import importlib
import io
import os
import sys

import numpy as np
from PIL import Image

REAL = {"REAL", "LIVE", "GENUINE", "BONAFIDE", "TRUE"}
FAKE = {"FAKE", "SPOOF", "ATTACK", "FALSE", "PRINT", "REPLAY"}


def normalize(res) -> dict:
    label = conf = faces = None
    if isinstance(res, dict):
        label = res.get("label")
        conf = res.get("confidence", res.get("conf", res.get("score")))
        faces = res.get("faces", res.get("face"))
    elif isinstance(res, (tuple, list)) and len(res) >= 2:
        label, conf = res[0], res[1]
    elif isinstance(res, bool):
        label = "REAL" if res else "FAKE"
    elif isinstance(res, (int, float)):
        conf = float(res)
    elif isinstance(res, str):
        label = res
    text = str(label).strip().upper() if label is not None else ""
    if conf is not None:
        conf = float(conf)
        conf = conf / 100 if conf > 1 else conf
    if text == "NO_FACE" or (faces == 0):
        return {"live": 0, "label": "NO_FACE", "confidence": 0.0, "face": 0, "b": 0, "m": 0, "engine": "custom"}
    if text in FAKE:
        p_real = 1 - conf if conf is not None else 0.05
    elif text in REAL:
        p_real = conf if conf is not None else 0.95
    elif conf is not None:
        p_real = conf
    else:
        raise ValueError(f"Cannot understand the model result: {res!r}")
    live = int(round(max(0.0, min(1.0, p_real)) * 100))
    name = "REAL" if live >= 70 else "BORDERLINE" if live >= 40 else "FAKE"
    return {"live": live, "label": name, "confidence": round(p_real, 4), "face": faces, "b": 0, "m": 0, "engine": "custom"}


class CustomVerifier:
    def __init__(self, spec: str, project_dir: str = "model_project", bgr: bool = True):
        if ":" not in spec:
            raise ValueError("FG_CUSTOM must look like module:function")
        module, _, func = spec.partition(":")
        folder = os.path.abspath(project_dir)
        for p in (folder, os.path.dirname(folder)):
            if p not in sys.path:
                sys.path.insert(0, p)
        os.chdir(folder) if os.path.isdir(folder) else None   # many projects load weights with relative paths
        self.fn = getattr(importlib.import_module(module), func)
        self.bgr = bgr

    def verify(self, image_bytes: bytes, session: str = "default") -> dict:
        frame = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        if self.bgr:
            frame = np.ascontiguousarray(frame[:, :, ::-1])
        return normalize(self.fn(frame))
