import datetime as dt
import os

import bcrypt
import jwt

# Set a long random value in production: set JWT_SECRET=...
SECRET_KEY = os.environ.get("JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
TOKEN_HOURS = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:  # e.g. the placeholder hash 'temp'
        return False


def create_token(user_id: int, role: str) -> str:
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TOKEN_HOURS)
    payload = {"sub": str(user_id), "role": role, "exp": expires}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
