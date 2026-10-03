import ipaddress
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .auth import get_current_user, require_admin
from .db import engine
from .ips import get_ip_row, snapshot

router = APIRouter(prefix="/api", tags=["edit"])


def log(conn, uid, action, etype, eid, old, new):
    conn.execute(
        text("""INSERT INTO audit_logs (user_id, action, entity_type, entity_id, old_value, new_value)
                VALUES (:u, :a, :t, :e, :o, :n)"""),
        {"u": uid, "a": action, "t": etype, "e": eid,
         "o": json.dumps(old, default=str), "n": json.dumps(new, default=str)},
    )


def clean(v):
    return (v or "").strip() or None


def dns_int(v):
    if not clean(v):
        return None
    try:
        return int(ipaddress.IPv4Address(v.strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid DNS address: {v}")


class VlanEdit(BaseModel):
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    location: Optional[str] = Field(None, min_length=1, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    primary_dns: Optional[str] = None
    secondary_dns: Optional[str] = None


@router.patch("/vlans/{vlan_pk}")
def edit_vlan(vlan_pk: int, data: VlanEdit, admin: dict = Depends(require_admin)):
    """Network, CIDR and gateway are not editable: they define the generated IP records."""
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    for k in ("primary_dns", "secondary_dns"):
        if k in changes:
            changes[k] = dns_int(changes[k])
    for k in ("department", "description"):
        if k in changes:
            changes[k] = clean(changes[k])

    with engine.connect() as conn:
        old = conn.execute(
            text("""SELECT vlan_id, name, location, department, description,
                           INET_NTOA(primary_dns) AS primary_dns, INET_NTOA(secondary_dns) AS secondary_dns
                    FROM vlans WHERE id = :i AND is_deleted = 0"""),
            {"i": vlan_pk},
        ).mappings().first()
        if not old:
            raise HTTPException(status_code=404, detail="VLAN not found.")
        if "vlan_id" in changes and conn.execute(
            text("SELECT 1 FROM vlans WHERE vlan_id = :v AND id <> :i"),
            {"v": changes["vlan_id"], "i": vlan_pk},
        ).first():
            raise HTTPException(status_code=409, detail=f"VLAN ID {changes['vlan_id']} already exists.")

        sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted by VlanEdit
        conn.execute(text(f"UPDATE vlans SET {sets} WHERE id = :pk"), {**changes, "pk": vlan_pk})
        log(conn, admin["id"], "VLAN_EDIT", "vlan", vlan_pk, dict(old), changes)
        conn.commit()
    return {"message": "VLAN updated."}


class IpEdit(BaseModel):
    department: Optional[str] = Field(None, max_length=100)
    room: Optional[str] = Field(None, max_length=50)
    equipment_id: Optional[str] = Field(None, max_length=50)
    equipment_name: Optional[str] = Field(None, max_length=100)
    cpu_serial: Optional[str] = Field(None, max_length=100)
    instrument_serial: Optional[str] = Field(None, max_length=100)
    user_name: Optional[str] = Field(None, max_length=100)
    remarks: Optional[str] = Field(None, max_length=500)


@router.patch("/ips/{ip_id}")
def edit_ip(ip_id: int, data: IpEdit, user: dict = Depends(get_current_user)):
    changes = {k: clean(v) for k, v in data.model_dump(exclude_unset=True).items()}
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    for k in ("equipment_id", "equipment_name"):
        if k in changes and not changes[k]:
            raise HTTPException(status_code=422, detail=f"{k.replace('_', ' ')} cannot be empty.")

    with engine.connect() as conn:
        old = get_ip_row(conn, ip_id)
        if old["status"] not in ("assigned", "inactive"):
            raise HTTPException(status_code=409, detail="Only assigned or inactive IPs can be edited.")
        sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted by IpEdit
        result = conn.execute(
            text(f"UPDATE ip_addresses SET {sets} WHERE id = :id AND status IN ('assigned','inactive')"),
            {**changes, "id": ip_id},
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="This IP was changed by someone else. Refresh and retry.")
        new = get_ip_row(conn, ip_id)
        log(conn, user["id"], "IP_EDIT", "ip", ip_id, snapshot(old), snapshot(new))
        conn.commit()
    return new


@router.get("/vlans/{vlan_pk}")
def get_vlan(vlan_pk: int, admin: dict = Depends(require_admin)):
    with engine.connect() as conn:
        row = conn.execute(
            text("""SELECT vlan_id, name, location, department, description,
                           INET_NTOA(primary_dns) AS primary_dns, INET_NTOA(secondary_dns) AS secondary_dns
                    FROM vlans WHERE id = :i AND is_deleted = 0"""),
            {"i": vlan_pk},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="VLAN not found.")
    return dict(row)
