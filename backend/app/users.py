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