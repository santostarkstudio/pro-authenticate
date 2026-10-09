#!/usr/bin/env python3
"""Scan your model project and tell FaceGuard how to connect it.

    python tools/inspect_project.py path/to/your/project

Prints a report, writes integration_report.json, and writes a draft models/model.json when it finds enough clues.
Read-only: it never changes your project.
"""
import json
import os
import re
import sys

MODEL_EXT = {".pt": "PyTorch / YOLO weights", ".pth": "PyTorch weights", ".h5": "Keras model", ".keras": "Keras model",
             ".onnx": "ONNX model", ".tflite": "TensorFlow Lite", ".pb": "TensorFlow graph", ".joblib": "scikit-learn", ".pkl": "pickle"}
SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", "env", "dataset", "datasets", "data"}
PATTERNS = {
    "yolo": r"\bYOLO\s*\(", "keras_load": r"load_model\s*\(", "torch_load": r"torch\.load\s*\(", "opencv_camera": r"cv2\.VideoCapture",
    "predict_call": r"\.predict\s*\(", "real_fake_words": r"\b(real|fake|spoof|live)\b",
}


def scan(root):
    files = {"models": [], "py": [], "reqs": []}
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x.lower() not in SKIP]
        if "saved_model.pb" in names:
            files["models"].append((os.path.relpath(d, root), "TensorFlow SavedModel folder", 0))
        for n in names:
            p = os.path.join(d, n)
            ext = os.path.splitext(n)[1].lower()
            if ext in MODEL_EXT:
                files["models"].append((os.path.relpath(p, root), MODEL_EXT[ext], os.path.getsize(p)))
            elif ext == ".py":
                files["py"].append(p)
            elif n.lower() in ("requirements.txt", "environment.yml", "pyproject.toml"):
                files["reqs"].append(os.path.relpath(p, root))
    return files


def analyse(root):
    files, hits, funcs, size, pre, order = scan(root), {k: [] for k in PATTERNS}, [], None, None, None
    for p in files["py"]:
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        rel = os.path.relpath(p, root)
        for k, rx in PATTERNS.items():
            if re.search(rx, text, re.I if k == "real_fake_words" else 0):
                hits[k].append(rel)
        for m in re.finditer(r"^def\s+(\w*(?:predict|detect|classif|liveness|verify|spoof)\w*)\s*\(([^)]*)\)", text, re.M | re.I):
            funcs.append({"file": rel, "function": m.group(1), "args": m.group(2).strip()})
        m = re.search(r"(?:resize|target_size|input_size|img_size|IMG_SIZE)\D{0,20}\(?\s*(\d{2,4})\s*,\s*(\d{2,4})", text)
        if m and not size:
            size = [int(m.group(1)), int(m.group(2))]
        if re.search(r"/\s*255", text):
            pre = pre or "div255"
        elif re.search(r"/\s*127\.5", text):
            pre = pre or "tanh"
        m = re.search(r"class_names\s*=\s*\[([^\]]+)\]|labels\s*=\s*\[([^\]]+)\]", text)
        if m:
            order = re.findall(r"['\"](\w+)['\"]", m.group(1) or m.group(2))
    yolo = [m for m in files["models"] if m[0].endswith(".pt")]
    cls = [m for m in files["models"] if m[0].endswith((".h5", ".keras")) or "SavedModel" in m[1]]
    real_index = None
    if order:
        low = [o.lower() for o in order]
        real_index = next((i for i, o in enumerate(low) if o in ("real", "live", "genuine")), None)
    cfg = {"yolo_path": "models/" + os.path.basename(yolo[0][0]) if yolo else "", "cls_path": "models/" + os.path.basename(cls[0][0]) if cls else "",
           "input_size": size or [224, 224], "real_index": real_index if real_index is not None else 1, "preprocess": pre or "div255", "yolo_conf": 0.4}
    notes = []
    if funcs:
        notes.append("Found functions that look like predictors. Best option: FG_VERIFIER=custom and point FG_CUSTOM at one of them.")
    if yolo and cls:
        notes.append("Found YOLO weights and a Keras model. Option: FG_VERIFIER=model with the draft models/model.json.")
    if hits["opencv_camera"]:
        notes.append("Your code opens the camera itself (cv2.VideoCapture). It must be reorganized into a function that receives a frame. Share the folder and the assistant will do this.")
    if size is None:
        notes.append("Could not guess the classifier input size. Check the model.json value.")
    if order is None:
        notes.append("Could not find the class order. Check which output index means REAL.")
    return {"root": os.path.abspath(root), "model_files": files["models"], "requirements": files["reqs"], "python_files": len(files["py"]),
            "uses": {k: v for k, v in hits.items() if v}, "candidate_functions": funcs, "guess": cfg, "notes": notes}


if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.path.isdir(sys.argv[1]):
        sys.exit(__doc__)
    r = analyse(sys.argv[1])
    print(f"\nProject: {r['root']}\nPython files: {r['python_files']}   Requirements: {', '.join(r['requirements']) or 'none found'}")
    print("\nModel files:")
    for f, kind, size in r["model_files"] or [("none found", "", 0)]:
        print(f"  {f}  ({kind}{', %.1f MB' % (size / 1e6) if size else ''})")
    print("\nFound in code:", ", ".join(r["uses"]) or "nothing recognised")
    print("\nFunctions that may be the predictor:")
    for f in r["candidate_functions"][:10] or [{"file": "none", "function": "", "args": ""}]:
        print(f"  {f['file']}: {f['function']}({f['args']})")
    print("\nDraft models/model.json:\n" + json.dumps(r["guess"], indent=2))
    print("\nNext steps:\n  " + "\n  ".join(r["notes"] or ["Share the folder and the assistant will finish the connection."]))
    json.dump(r, open("integration_report.json", "w"), indent=2)
    print("\nSaved integration_report.json")
