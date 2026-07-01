import os
import hashlib
import base64
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature
from fastapi import Request, HTTPException

SECRET_KEY = os.getenv("WEBAPI_SECRET_KEY", "dev-secret-change-me")
APP_PASSWORD_HASH = os.getenv("WEBAPI_PASSWORD_HASH", "")  # generate via hash_password.py, never store plaintext
SESSION_COOKIE = "session"

serializer = URLSafeTimedSerializer(SECRET_KEY)


def _prehash(plain: str) -> bytes:
    """SHA-256 pre-hash so bcrypt's 72-byte input limit never truncates a long
    passphrase. Output is fixed-length base64, well under bcrypt's limit."""
    return base64.b64encode(hashlib.sha256(plain.encode("utf-8")).digest())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str) -> bool:
    if not APP_PASSWORD_HASH:
        raise RuntimeError("WEBAPI_PASSWORD_HASH not set in environment")
    return bcrypt.checkpw(_prehash(plain), APP_PASSWORD_HASH.encode("utf-8"))


def create_session_token(username: str = "owner") -> str:
    return serializer.dumps({"user": username})


def require_session(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = serializer.loads(token, max_age=60 * 60 * 24 * 7)  # 7-day session
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return data
