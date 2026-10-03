import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .auth import require_admin
from .db import engine
from .security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    email: Optional[str] = None
    password: str = Field(min_length=8, max_length=64)
    role: Literal["admin", "user"] = "user"


@router.post("", status_code=201)
def create_user(data: UserIn, admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        if conn.execute(
            text("SELECT 1 FROM users WHERE username = :u"), {"u": data.username}
        ).first():
            raise HTTPException(status_code=409, detail="Username already exists.")

        result = conn.execute(
            text(
                """INSERT INTO users (username, full_name, email, password_hash, role)
                   VALUES (:u, :f, :e, :p, :r)"""
            ),
            {"u": data.username, "f": data.full_name, "e": data.email,
             "p": hash_password(data.password), "r": data.role},
        )
        user_id = result.lastrowid
        conn.execute(
            text(
                """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, new_value)
                   VALUES (:uid, 'USER_CREATE', 'user', :eid, :val)"""
            ),
            {"uid": admin["id"], "eid": user_id,
             "val": json.dumps({"username": data.username, "role": data.role})},
        )
        conn.commit()
    return {"id": user_id, "username": data.username, "role": data.role}


@router.get("")
def list_users(admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT id, username, full_name, email, role, is_active, created_at
                   FROM users ORDER BY id"""
            )
        ).mappings().all()
    return [dict(r) for r in rows]


class UserEdit(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=150)
    role: Optional[Literal["admin", "user"]] = None
    is_active: Optional[bool] = None


class PasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=64)


def log_user(conn, uid, action, eid, old, new):
    conn.execute(
        text("""INSERT INTO audit_logs (user_id, action, entity_type, entity_id, old_value, new_value)
                VALUES (:u, :a, 'user', :e, :o, :n)"""),
        {"u": uid, "a": action, "e": eid,
         "o": json.dumps(old, default=str), "n": json.dumps(new, default=str)},
    )


@router.patch("/{user_id}")
def edit_user(user_id: int, data: UserEdit, admin: dict = Depends(require_admin)):
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    if "is_active" in changes:
        changes["is_active"] = int(changes["is_active"])
    if "email" in changes:
        changes["email"] = (changes["email"] or "").strip() or None
    if user_id == admin["id"] and (changes.get("is_active") == 0 or changes.get("role") == "user"):
        raise HTTPException(status_code=409, detail="You cannot deactivate or demote your own account.")

    with engine.connect() as conn:
        old = conn.execute(
            text("SELECT full_name, email, role, is_active FROM users WHERE id = :i"), {"i": user_id}
        ).mappings().first()
        if not old:
            raise HTTPException(status_code=404, detail="User not found.")
        sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted by UserEdit
        conn.execute(text(f"UPDATE users SET {sets} WHERE id = :id"), {**changes, "id": user_id})
        log_user(conn, admin["id"], "USER_EDIT", user_id, dict(old), changes)
        conn.commit()
    return {"message": "User updated."}


@router.post("/{user_id}/password")
def reset_password(user_id: int, data: PasswordIn, admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET password_hash = :h WHERE id = :id"),
            {"h": hash_password(data.new_password), "id": user_id},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=404, detail="User not found.")
        log_user(conn, admin["id"], "USER_PASSWORD_RESET", user_id, {}, {})  # password is never logged
        conn.commit()
    return {"message": "Password reset."}