"""Signed bearer-token authentication for the prototype.

- Tokens are HMAC-SHA256 signed (sub, role, exp). The role is derived on the server from the user id,
  never taken from a request header.
- Login is a demo one-time-code check (DEMO_OTP). In production this is replaced by UAE Pass / OTP;
  the rest of the system only depends on the verified token.
- Legacy header auth (X-User-Id / X-User-Role) works ONLY when ALLOW_HEADER_AUTH=1 (tests / local scripts).
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Dict, Optional

from fastapi import Header, HTTPException

from backend.database import db

TOKEN_TTL_SECONDS = 8 * 3600
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
_failed: Dict[str, list] = {}


def _secret() -> bytes:
    return os.environ.get("AUTH_SECRET", "demo_insecure_jwt_secret_change_in_production").encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def role_for(user_id: str) -> str:
    """Role is a property of the account, decided server-side."""
    if user_id.startswith("admin_"):
        return "admin"
    if user_id.startswith("counsellor_"):
        return "counsellor"
    if user_id.startswith("lab_"):
        return "lab"
    return "patient"


def issue_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = _b64(json.dumps({"sub": user_id, "role": role_for(user_id), "exp": int(time.time()) + ttl}).encode("utf-8"))
    sig = _b64(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> Optional[Dict[str, str]]:
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < time.time():
            return None
        return {"user_id": data["sub"], "role": data["role"]}
    except Exception:
        return None


def account_exists(user_id: str) -> bool:
    if role_for(user_id) in ("admin", "counsellor", "lab"):
        return True  # staff accounts are provisioned outside the person table in this prototype
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM person WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def login(user_id: str, otp: str) -> str:
    now = time.time()
    attempts = [t for t in _failed.get(user_id, []) if now - t < LOCKOUT_SECONDS]
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    expected = os.environ.get("DEMO_OTP", "123456")
    if not account_exists(user_id) or not hmac.compare_digest(str(otp), expected):
        attempts.append(now)
        _failed[user_id] = attempts
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    _failed.pop(user_id, None)
    return issue_token(user_id)


def current_user(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> Dict[str, str]:
    if authorization and authorization.lower().startswith("bearer "):
        user = verify_token(authorization[7:].strip())
        if user:
            return user
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if os.environ.get("ALLOW_HEADER_AUTH") == "1":
        return {"user_id": x_user_id or "person_001", "role": x_user_role or "patient"}
    raise HTTPException(status_code=401, detail="Authentication required.")


def require_staff(user: Dict[str, str]) -> Dict[str, str]:
    if user["role"] not in ("counsellor", "admin"):
        raise HTTPException(status_code=403, detail="Counsellor or admin role required.")
    return user


def require_roles(user: Dict[str, str], *roles: str) -> Dict[str, str]:
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Role not permitted for this action.")
    return user
