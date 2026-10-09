#!/usr/bin/env python3
"""Before-you-deploy checklist.   python scripts/check.py"""
import io
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rows = []


def add(status, name, hint=""):
    rows.append((status, name, hint))


def env():
    out = {}
    p = os.path.join(ROOT, ".env")
    for line in open(p) if os.path.exists(p) else []:
        line = line.split("#")[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    e = env()
    add("PASS" if sys.version_info >= (3, 10) else "FAIL", "Python 3.10 or newer", sys.version.split()[0])
    for m in ("fastapi", "uvicorn", "jwt", "PIL", "numpy"):
        try:
            __import__(m)
            add("PASS", f"package {m}")
        except ImportError:
            add("FAIL", f"package {m}", "pip install -r backend/requirements.txt")
    add("PASS" if e.get("FG_SECRET", "") not in ("", "change-this-to-a-long-random-string", "dev-secret-change-me") else "FAIL", "Secret changed", "run scripts/run_local.py once to create .env")
    add("PASS" if e.get("FG_ADMIN_PASSWORD", "demo") not in ("demo", "change-me-now", "") else "WARN", "Admin password changed", "edit FG_ADMIN_PASSWORD in .env")
    mode = e.get("FG_VERIFIER", "demo")
    add("PASS" if mode != "demo" else "WARN", f"Verification engine: {mode}", "demo is only a placeholder; connect your model before real use")
    if mode == "model":
        for k in ("FG_YOLO_PATH", "FG_CLS_PATH"):
            p = os.path.join(ROOT, "backend", e.get(k, ""))
            add("PASS" if os.path.exists(p) else "FAIL", f"{k} file exists", p)
    if mode == "custom":
        add("PASS" if e.get("FG_CUSTOM") else "FAIL", "FG_CUSTOM set (module:function)")
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_core.py"], cwd=os.path.join(ROOT, "backend"), capture_output=True, text=True)
    add("PASS" if r.returncode == 0 else "FAIL", "Unit tests", r.stderr.strip().splitlines()[-1] if r.stderr else "")
    try:
        from PIL import Image
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        os.chdir(os.path.join(ROOT, "backend"))
        for k, v in e.items():
            os.environ.setdefault(k, v)
        from app.config import Settings
        from app.verifier import get_verifier
        buf = io.BytesIO()
        Image.new("RGB", (320, 240), (120, 120, 120)).save(buf, "JPEG")
        res = get_verifier(Settings()).verify(buf.getvalue(), "check")
        add("PASS", "Engine answers on a test image", f"{res['engine']}: live {res['live']} {res['label']}")
    except Exception as ex:
        add("FAIL", "Engine answers on a test image", str(ex)[:120])
    w = max(len(n) for _, n, _ in rows)
    for s, n, h in rows:
        print(f"[{s}] {n.ljust(w)}  {h}")
    sys.exit(1 if any(s == "FAIL" for s, _, _ in rows) else 0)


if __name__ == "__main__":
    main()
