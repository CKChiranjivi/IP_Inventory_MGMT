from .auth import require_admin as get_current_admin
import ipaddress
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from .db import engine
from .ipcalc import PlanError, build_plan

router = APIRouter(prefix="/api/vlans", tags=["vlans"])

BATCH_SIZE = 1000
LOCK_NAME = "vlan_create"


class VlanIn(BaseModel):
    vlan_id: int = Field(ge=1, le=4094)
    name: str = Field(min_length=1, max_length=100)
    network_address: str
    cidr: int
    gateway: str
    primary_dns: Optional[str] = None
    secondary_dns: Optional[str] = None
    location: str = Field(min_length=1, max_length=100)
    department: Optional[str] = None
    description: Optional[str] = None
    reserved_ips: list[str] = []


def make_plan(data: VlanIn):
    try:
        return build_plan(data.network_address, data.cidr, data.gateway, data.reserved_ips)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def dns_to_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid DNS address: {value}")


def find_overlaps(conn, start: int, end: int) -> list[dict]:
    """Any row returned is a conflict: duplicate, subset or superset.
    Soft-deleted VLANs are included on purpose, because their IP rows still exist
    and would violate the unique constraint on ip_addresses.ip_address."""
    rows = conn.execute(
        text(
            """SELECT vlan_id, name, INET_NTOA(network_address) AS network, cidr
               FROM vlans
               WHERE :s <= range_end AND :e >= range_start"""
        ),
        {"s": start, "e": end},
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/preview")
def preview_vlan(data: VlanIn, admin=Depends(get_current_admin)):
    plan = make_plan(data)
    dns_to_int(data.primary_dns)
    dns_to_int(data.secondary_dns)
    with engine.connect() as conn:
        conflicts = find_overlaps(conn, plan.range_start, plan.range_end)
        vlan_taken = conn.execute(
            text("SELECT 1 FROM vlans WHERE vlan_id = :v"), {"v": data.vlan_id}
        ).first() is not None
    return {
        "summary": plan.summary(),
        "rows": plan.preview_rows(),
        "conflicts": conflicts,
        "vlan_id_taken": vlan_taken,
        "can_create": not conflicts and not vlan_taken,
    }


@router.post("", status_code=201)
def create_vlan(data: VlanIn, admin=Depends(get_current_admin)):
    plan = make_plan(data)
    primary = dns_to_int(data.primary_dns)
    secondary = dns_to_int(data.secondary_dns)

    with engine.connect() as conn:
        # One admin at a time, so the overlap check and the inserts are atomic.
        locked = conn.execute(text("SELECT GET_LOCK(:n, 10)"), {"n": LOCK_NAME}).scalar()
        if locked != 1:
            raise HTTPException(status_code=503, detail="Another VLAN is being created. Try again.")
        try:
            conflicts = find_overlaps(conn, plan.range_start, plan.range_end)
            if conflicts:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "This network range already exists or overlaps.",
                            "conflicts": conflicts},
                )

            if conn.execute(
                text("SELECT 1 FROM vlans WHERE vlan_id = :v"), {"v": data.vlan_id}
            ).first():
                raise HTTPException(status_code=409, detail=f"VLAN ID {data.vlan_id} already exists.")

            result = conn.execute(
                text(
                    """INSERT INTO vlans
                       (vlan_id, name, network_address, cidr, range_start, range_end,
                        gateway_ip, primary_dns, secondary_dns, location, department,
                        description, created_by)
                       VALUES
                       (:vlan_id, :name, :net, :cidr, :rs, :re,
                        :gw, :dns1, :dns2, :loc, :dept, :descr, :uid)"""
                ),
                {
                    "vlan_id": data.vlan_id, "name": data.name,
                    "net": plan.range_start, "cidr": data.cidr,
                    "rs": plan.range_start, "re": plan.range_end,
                    "gw": plan.gateway, "dns1": primary, "dns2": secondary,
                    "loc": data.location, "dept": data.department,
                    "descr": data.description, "uid": admin["id"],
                },
            )
            vlan_pk = result.lastrowid

            insert_ip = text(
                """INSERT INTO ip_addresses (vlan_pk, ip_address, status, reserved_reason)
                   VALUES (:v, :ip, :s, :r)"""
            )
            batch = []
            for ip, status, reason in plan.rows():
                batch.append({"v": vlan_pk, "ip": ip, "s": status, "r": reason})
                if len(batch) >= BATCH_SIZE:
                    conn.execute(insert_ip, batch)
                    batch = []
            if batch:
                conn.execute(insert_ip, batch)

            conn.execute(
                text(
                    """INSERT INTO audit_logs (user_id, action, entity_type, entity_id, new_value)
                       VALUES (:uid, 'VLAN_CREATE', 'vlan', :eid, :val)"""
                ),
                {"uid": admin["id"], "eid": vlan_pk,
                 "val": json.dumps({**plan.summary(), "vlan_id": data.vlan_id, "name": data.name})},
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})
            conn.commit()

    return {"id": vlan_pk, "vlan_id": data.vlan_id, "usable_ips": plan.usable,
            "message": "VLAN created and IP records generated."}


@router.get("")
def list_vlans(admin=Depends(get_current_admin)):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT v.id, v.vlan_id, v.name,
                          INET_NTOA(v.network_address) AS network, v.cidr,
                          v.location, v.department,
                          COUNT(i.id) AS total_usable,
                          COALESCE(SUM(i.status = 'assigned'), 0)  AS assigned,
                          COALESCE(SUM(i.status = 'available'), 0) AS available,
                          COALESCE(SUM(i.status = 'reserved'), 0)  AS reserved,
                          COALESCE(SUM(i.status = 'inactive'), 0)  AS inactive
                   FROM vlans v
                   LEFT JOIN ip_addresses i ON i.vlan_pk = v.id
                   WHERE v.is_deleted = 0
                   GROUP BY v.id
                   ORDER BY v.vlan_id"""
            )
        ).mappings().all()

    out = []
    for r in rows:
        d = {k: (int(v) if k in ("total_usable", "assigned", "available", "reserved", "inactive") else v)
             for k, v in r.items()}
        d["utilization_pct"] = round(d["assigned"] / d["total_usable"] * 100, 2) if d["total_usable"] else 0
        out.append(d)
    return out