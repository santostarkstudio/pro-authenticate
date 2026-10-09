#!/usr/bin/env python3
"""One command to run FaceGuard on this computer and test it from phones and tablets.

    python scripts/run_local.py            # http://localhost:8000
    python scripts/run_local.py --https    # also works for the camera on phones and tablets (self-signed certificate)
"""
import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_env():
    env, example = os.path.join(ROOT, ".env"), os.path.join(ROOT, ".env.example")
    if not os.path.exists(env) and os.path.exists(example):
        text = open(example).read().replace("change-this-to-a-long-random-string", secrets.token_urlsafe(32))
        open(env, "w").write(text)
        print("Created .env with a random secret. Change FG_ADMIN_PASSWORD in it before sharing the link.")
    for line in open(env) if os.path.exists(env) else []:
        line = line.split("#")[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def make_cert(ip):
    d = os.path.join(ROOT, "certs")
    os.makedirs(d, exist_ok=True)
    key, crt = os.path.join(d, "key.pem"), os.path.join(d, "cert.pem")
    if not os.path.exists(crt):
        if not shutil.which("openssl"):
            sys.exit("openssl was not found. Install it, or use a tunnel instead (see docs/DEVICE_TESTING.md).")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt, "-days", "365",
                        "-subj", "/CN=faceguard", "-addext", f"subjectAltName=IP:{ip},DNS:localhost"], check=True, capture_output=True)
    return key, crt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https", action="store_true")
    a = ap.parse_args()
    ensure_env()
    try:
        import uvicorn
    except ImportError:
        sys.exit("Run first:  pip install -r backend/requirements.txt")
    ip, scheme = lan_ip(), "https" if a.https else "http"
    kw = {}
    if a.https:
        kw["ssl_keyfile"], kw["ssl_certfile"] = make_cert(ip)
    print(f"\nOn this computer : {scheme}://localhost:{a.port}\nPhone or tablet  : {scheme}://{ip}:{a.port}   (same Wi-Fi)")
    print("Staff page       : add  #/admin  to the address\n" + ("" if a.https else "Note: phones only allow the camera on HTTPS. Use --https for phone and tablet tests.\n"))
    os.chdir(os.path.join(ROOT, "backend"))
    sys.path.insert(0, os.getcwd())
    uvicorn.run("app.main:app", host="0.0.0.0", port=a.port, **kw)


if __name__ == "__main__":
    main()
