"""Config-driven YOLO + Keras pipeline (the pipeline in your report). No code edits: fill backend/models/model.json.

{ "yolo_path": "models/yolo_face.pt", "cls_path": "models/liveness.keras",
  "input_size": [224, 224], "real_index": 1, "preprocess": "div255", "yolo_conf": 0.4 }
preprocess: div255 | none | tanh (x/127.5-1) | imagenet
`python tools/inspect_project.py <your folder>` writes a draft of this file for you.
"""
import io
import json
import os

import numpy as np
from PIL import Image

DEFAULTS = {"input_size": [224, 224], "real_index": 1, "preprocess": "div255", "yolo_conf": 0.4}


def prepare(face: np.ndarray, mode: str) -> np.ndarray:
    x = face.astype(np.float32)
    if mode == "div255":
        x = x / 255.0
    elif mode == "tanh":
        x = x / 127.5 - 1.0
    elif mode == "imagenet":
        x = (x / 255.0 - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    return x[None].astype(np.float32)


def real_probability(pred: np.ndarray, real_index: int) -> float:
    pred = np.asarray(pred).reshape(-1)
    if pred.size == 1:                       # single sigmoid output
        return float(pred[0]) if real_index == 1 else 1.0 - float(pred[0])
    return float(pred[real_index])


class ModelVerifier:
    def __init__(self, yolo_path, cls_path, bgr=True, input_size=(224, 224), real_index=1, preprocess="div255", yolo_conf=0.4):
        from tensorflow import keras
        from ultralytics import YOLO          # imported lazily so the demo needs no ML packages
        self.yolo, self.cls = YOLO(yolo_path), keras.models.load_model(cls_path)
        self.bgr, self.size, self.idx, self.pre, self.conf = bgr, tuple(input_size), real_index, preprocess, yolo_conf

    @classmethod
    def from_json(cls, cfg_path, yolo_path, cls_path, bgr=True):
        opt = dict(DEFAULTS)
        if os.path.exists(cfg_path):
            opt.update(json.load(open(cfg_path)))
        return cls(opt.pop("yolo_path", yolo_path), opt.pop("cls_path", cls_path), bgr=opt.pop("bgr", bgr),
                   input_size=opt["input_size"], real_index=opt["real_index"], preprocess=opt["preprocess"], yolo_conf=opt["yolo_conf"])

    def verify(self, image_bytes: bytes, session: str = "default") -> dict:
        frame = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        if self.bgr:                           # match how your project fed frames (OpenCV = BGR)
            frame = np.ascontiguousarray(frame[:, :, ::-1])
        boxes = self.yolo(frame, conf=self.conf, verbose=False)[0].boxes.xyxy.cpu().numpy()
        if len(boxes) == 0:
            return {"live": 0, "label": "NO_FACE", "confidence": 0.0, "face": 0, "b": 0, "m": 0, "engine": "model"}
        x1, y1, x2, y2 = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])).astype(int)
        crop = frame[max(y1, 0):y2, max(x1, 0):x2]
        crop = np.asarray(Image.fromarray(crop[:, :, ::-1] if self.bgr else crop).resize(self.size))
        if self.bgr:
            crop = np.ascontiguousarray(crop[:, :, ::-1])
        p = real_probability(self.cls.predict(prepare(crop, self.pre), verbose=0), self.idx)
        live = int(round(p * 100))
        return {"live": live, "label": "REAL" if live >= 70 else "BORDERLINE" if live >= 40 else "FAKE",
                "confidence": round(p, 4), "face": int(len(boxes)), "b": 0, "m": 0, "engine": "model"}
