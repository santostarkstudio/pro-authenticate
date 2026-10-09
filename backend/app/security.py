import base64
import hashlib
import hmac
import os
import secrets
import time

import jwt

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(digest))
    except Exception:
        return False


def make_token(secret: str, sub: str, role: str, hours: int = 8, **claims) -> str:
    payload = {"sub": sub, "role": role, "exp": int(time.time()) + hours * 3600, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def read_token(secret: str, token: str):
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


class Tickets:
    """Short-lived, single-use tickets so no long-lived token ever appears in a WebSocket URL (URLs get logged)."""
    def __init__(self, ttl: int = 30):
        self.ttl, self.items = ttl, {}

    def _gc(self):
        now = time.time()
        for k in [k for k, (exp, _) in self.items.items() if exp < now]:
            del self.items[k]

    def issue(self, claims: dict) -> str:
        self._gc()
        t = secrets.token_urlsafe(24)
        self.items[t] = (time.time() + self.ttl, claims)
        return t

    def redeem(self, ticket: str):
        self._gc()
        hit = self.items.pop(ticket, None)
        return hit[1] if hit else None
