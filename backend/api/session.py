"""Signed session cookie: who is logged in, never what they may do.

The cookie holds only the user name and an expiry, signed with HMAC-SHA256.
The role is read from the staff sheet on every request, so a role change in
the sheet takes effect immediately and the client can't claim a role.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

COOKIE = "geri_session"
MAX_AGE = 12 * 3600


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(secret: str, name: str, now: float | None = None) -> str:
    payload = _b64(json.dumps({"n": name, "e": int((now or time.time()) + MAX_AGE)}, ensure_ascii=False).encode())
    mac = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{mac}"


def verify(secret: str, token: str | None, now: float | None = None) -> str | None:
    """Return the user name for a valid, unexpired token, else None."""
    if not token or "." not in token:
        return None
    payload, mac = token.rsplit(".", 1)
    good = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, good):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if int(data.get("e", 0)) < (now or time.time()):
        return None
    return str(data.get("n") or "") or None
