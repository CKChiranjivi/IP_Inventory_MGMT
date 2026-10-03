import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text

from .auth import get_current_user
from .db import engine
from .ips import FROM_JOIN, IP_COLUMNS, Status

router = APIRouter(prefix="/api", tags=["dashboard"])

NUM = ("total", "assigned", "available", "reserved", "inactive")


def pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0


@router.get("/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT v.id, v.vlan_id, v.name, INET_NTOA(v.network_address) AS network,
                          v.cidr, v.location, v.department,
                          COUNT(i.id) AS total,
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

    vlans = []
    for r in rows:
        d = {k: (int(v) if k in NUM else v) for k, v in r.items()}
        d["utilization_pct"] = pct(d["assigned"], d["total"])  # assigned / total usable
        vlans.append(d)
    totals = {k: sum(v[k] for v in vlans) for k in NUM}
    totals["utilization_pct"] = pct(totals["assigned"], totals["total"])
    return {"totals": totals, "vlans": vlans}


def safe(value) -> str:
    """Stop spreadsheet formula injection: cells starting with = + - @ are prefixed."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/export/ips.csv")
def export_ips(
    vlan_pk: Optional[int] = None,
    status: Optional[Status] = None,
    q: Optional[str] = Query(None, max_length=100),
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

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {IP_COLUMNS} {FROM_JOIN} WHERE {' AND '.join(where)} ORDER BY i.ip_address"),
            params,
        ).mappings().all()

    cols = [("IP Address", "ip"), ("VLAN ID", "vlan_id"), ("VLAN Name", "vlan_name"),
            ("Location", "location"), ("Department", "department"), ("Status", "status"),
            ("Room", "room"), ("Equipment ID", "equipment_id"), ("Equipment Name", "equipment_name"),
            ("CPU S/N", "cpu_serial"), ("Instrument S/N", "instrument_serial"),
            ("User Name", "user_name"), ("Remarks", "remarks"), ("Assigned At", "assigned_at")]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c[0] for c in cols])
    for r in rows:
        writer.writerow([safe(r[c[1]]) for c in cols])

    return Response(
        content="\ufeff" + buf.getvalue(),  # BOM so Excel reads UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ip_inventory.csv"'},
    )
