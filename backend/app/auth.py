import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import text

from .db import engine
from .security import create_token, decode_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    bad_token = HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = int(decode_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise bad_token

    # Re-check the database so deactivated users lose access immediately.
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, username, full_name, role, is_active FROM users WHERE id = :i"),
            {"i": user_id},
        ).mappings().first()
    if not row or not row["is_active"]:
        raise bad_token
    return dict(row)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT id, username, full_name, role, password_hash, is_active
                   FROM users WHERE username = :u"""
            ),
            {"u": form.username},
        ).mappings().first()

    if not row or not row["is_active"] or not verify_password(form.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    return {
        "access_token": create_token(row["id"], row["role"]),
        "token_type": "bearer",
        "user": {"id": row["id"], "username": row["username"],
                 "full_name": row["full_name"], "role": row["role"]},
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user