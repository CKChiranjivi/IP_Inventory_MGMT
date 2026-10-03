import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from .auth import get_current_user
from .db import engine

router = APIRouter(prefix="/api/ips", tags=["ips"])

Status = Literal["available", "assigned", "reserved", "inactive"]

# Allowed status changes. Normal Users cannot touch reserved IPs.
USER_TRANSITIONS = {("assigned", "inactive"), ("inactive", "assigned")}
ADMIN_TRANSITIONS = USER_TRANSITIONS | {("available", "reserved"), ("reserved", "available")}

IP_COLUMNS = """i.id, INET_NTOA(i.ip_address) AS ip, i.status, i.reserved_reason,
    i.room, i.equipment_id, i.equipment_name, i.cpu_serial, i.instrument_serial,
    i.user_name, i.remarks, i.assigned_at,
    v.vlan_id, v.name AS vlan_name, v.location,
    COALESCE(i.department, v.department) AS department"""

FROM_JOIN = "FROM ip_addresses i JOIN vlans v ON v.id = i.vlan_pk"


class AssignIn(BaseModel):
    department: Optional[str] = Field(None, max_length=100)
    room: Optional[str] = Field(None, max_length=50)
    equipment_id: str = Field(min_length=1, max_length=50)
    equipment_name: str = Field(min_length=1, max_length=100)
    cpu_serial: Optional[str] = Field(None, max_length=100)
    instrument_serial: Optional[str] = Field(None, max_length=100)
    user_name: Optional[str] = Field(None, max_length=100)
    remarks: Optional[str] = Field(None, max_length=500)


class StatusIn(BaseModel):
    status: Status
    reserved_reason: Optional[str] = Field(None, max_length=100)


def get_ip_row(conn, ip_id: int) -> dict:
    row = conn.execute(
        text(f"SELECT {IP_COLUMNS} {FROM_JOIN} WHERE i.id = :id AND v.is_deleted = 0"),
        {"id": ip_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="IP address not found.")
    return dict(row)


def snapshot(row: dict) -> dict:
    keys = ("ip", "status", "reserved_reason", "department", "room", "equipment_id",
            "equipment_name", "cpu_serial", "instrument_serial", "user_name", "remarks")
    return {k: row.get(k) for k in keys}


def audit(conn, user_id: int, action: str, ip_id: int, old: dict, new: dict) -> None:
    conn.execute(
        text(
            """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, old_value, new_value)
               VALUES (:uid, :act, 'ip', :eid, :old, :new)"""
        ),
        {"uid": user_id, "act": action, "eid": ip_id,
         "old": json.dumps(old, default=str), "new": json.dumps(new, default=str)},
    )


# ---------------------------------------------------------------- read endpoints

@router.get("/vlans")
def vlans_for_dropdown(user: dict = Depends(get_current_user)):
    """Read-only VLAN list for the Assign IP screen (any logged-in user)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT v.id, v.vlan_id, v.name, INET_NTOA(v.network_address) AS network,
                          v.cidr, v.location, v.department,
                          COALESCE(SUM(i.status = 'available'), 0) AS available
                   FROM vlans v
                   LEFT JOIN ip_addresses i ON i.vlan_pk = v.id
                   WHERE v.is_deleted = 0
                   GROUP BY v.id
                   ORDER BY v.vlan_id"""
            )
        ).mappings().all()
    return [{**dict(r), "available": int(r["available"])} for r in rows]


@router.get("/available")
def available_ips(
    vlan_pk: int,
    limit: int = Query(500, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT i.id, INET_NTOA(i.ip_address) AS ip
                   FROM ip_addresses i JOIN vlans v ON v.id = i.vlan_pk
                   WHERE i.vlan_pk = :v AND i.status = 'available' AND v.is_deleted = 0
                   ORDER BY i.ip_address
                   LIMIT :lim"""
            ),
            {"v": vlan_pk, "lim": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("")
def list_ips(
    vlan_pk: Optional[int] = None,
    status: Optional[Status] = None,
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    where = ["v.is_deleted = 0"]
    params: dict = {}
    if vlan_pk:
        where.append("i.vlan_pk = :vlan_pk")
        params["vlan_pk"] = vlan_pk
    if status:
        where.append("i.status = :status")
        params["status"] = status
    if q and q.strip():
        where.append(
            """(INET_NTOA(i.ip_address) LIKE :q OR i.equipment_id LIKE :q
                OR i.equipment_name LIKE :q OR i.user_name LIKE :q
                OR i.cpu_serial LIKE :q OR i.instrument_serial LIKE :q)"""
        )
        params["q"] = f"%{q.strip()}%"
    where_sql = " AND ".join(where)

    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) {FROM_JOIN} WHERE {where_sql}"), params
        ).scalar()
        rows = conn.execute(
            text(
                f"""SELECT {IP_COLUMNS} {FROM_JOIN} WHERE {where_sql}
                    ORDER BY i.ip_address LIMIT :limit OFFSET :offset"""
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        ).mappings().all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [dict(r) for r in rows]}


# ---------------------------------------------------------------- write endpoints

@router.post("/{ip_id}/assign")
def assign_ip(ip_id: int, data: AssignIn, user: dict = Depends(get_current_user)):
    with engine.connect() as conn:
        old = get_ip_row(conn, ip_id)

        # Conditional update: if two people click at once, only one row changes.
        result = conn.execute(
            text(
                """UPDATE ip_addresses
                   SET status = 'assigned', department = :dept, room = :room, equipment_id = :eq_id,
                       equipment_name = :eq_name, cpu_serial = :cpu,
                       instrument_serial = :inst, user_name = :uname, remarks = :rem,
                       assigned_by = :uid, assigned_at = NOW()
                   WHERE id = :id AND status = 'available'"""
            ),
            {"dept": data.department, "room": data.room, "eq_id": data.equipment_id, "eq_name": data.equipment_name,
             "cpu": data.cpu_serial, "inst": data.instrument_serial,
             "uname": data.user_name, "rem": data.remarks,
             "uid": user["id"], "id": ip_id},
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail=f"IP {old['ip']} is no longer available (status: {old['status']}). Please pick another.",
            )

        new = get_ip_row(conn, ip_id)
        audit(conn, user["id"], "IP_ASSIGN", ip_id, snapshot(old), snapshot(new))
        conn.commit()
    return new


@router.post("/{ip_id}/release")
def release_ip(ip_id: int, user: dict = Depends(get_current_user)):
    with engine.connect() as conn:
        old = get_ip_row(conn, ip_id)
        if old["status"] not in ("assigned", "inactive"):
            raise HTTPException(
                status_code=409,
                detail=f"Only assigned or inactive IPs can be released (current status: {old['status']}).",
            )

        result = conn.execute(
            text(
                """UPDATE ip_addresses
                   SET status = 'available', room = NULL, equipment_id = NULL,
                       equipment_name = NULL, cpu_serial = NULL, instrument_serial = NULL,
                       user_name = NULL, remarks = NULL, department = NULL, assigned_by = NULL, assigned_at = NULL
                   WHERE id = :id AND status = :old_status"""
            ),
            {"id": ip_id, "old_status": old["status"]},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="This IP was changed by someone else. Refresh and retry.")

        new = get_ip_row(conn, ip_id)
        audit(conn, user["id"], "IP_RELEASE", ip_id, snapshot(old), snapshot(new))
        conn.commit()
    return new


@router.post("/{ip_id}/status")
def change_status(ip_id: int, data: StatusIn, user: dict = Depends(get_current_user)):
    with engine.connect() as conn:
        old = get_ip_row(conn, ip_id)
        pair = (old["status"], data.status)
        allowed = ADMIN_TRANSITIONS if user["role"] == "admin" else USER_TRANSITIONS

        if pair not in allowed:
            if pair in ADMIN_TRANSITIONS:
                raise HTTPException(status_code=403, detail="Only an Admin can reserve or unreserve IPs.")
            raise HTTPException(
                status_code=409,
                detail=f"Cannot change status from {pair[0]} to {pair[1]}. Use assign or release instead.",
            )
        if old["status"] == "reserved" and old["reserved_reason"] == "Gateway":
            raise HTTPException(status_code=409, detail="The gateway address cannot be changed.")

        reason = (data.reserved_reason or "Reserved") if data.status == "reserved" else None
        result = conn.execute(
            text(
                """UPDATE ip_addresses SET status = :new, reserved_reason = :reason
                   WHERE id = :id AND status = :old"""
            ),
            {"new": data.status, "reason": reason, "id": ip_id, "old": old["status"]},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="This IP was changed by someone else. Refresh and retry.")

        new = get_ip_row(conn, ip_id)
        audit(conn, user["id"], "IP_STATUS_CHANGE", ip_id, snapshot(old), snapshot(new))
        conn.commit()
    return new
