import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from .auth import require_admin
from .db import engine

router = APIRouter(prefix="/api/audit", tags=["audit"])


def parse_json(value):
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


@router.get("")
def list_audit(
    action: Optional[str] = Query(None, max_length=50),
    entity_type: Optional[str] = Query(None, max_length=30),
    user_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_admin),
):
    where = ["1 = 1"]
    params: dict = {}
    if action:
        where.append("a.action = :action")
        params["action"] = action
    if entity_type:
        where.append("a.entity_type = :etype")
        params["etype"] = entity_type
    if user_id:
        where.append("a.user_id = :uid")
        params["uid"] = user_id
    where_sql = " AND ".join(where)

    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM audit_logs a WHERE {where_sql}"), params
        ).scalar()
        rows = conn.execute(
            text(
                f"""SELECT a.id, a.created_at, a.action, a.entity_type, a.entity_id,
                           u.username AS changed_by, u.full_name AS changed_by_name,
                           CASE a.entity_type
                             WHEN 'ip' THEN (SELECT INET_NTOA(ip_address)
                                             FROM ip_addresses WHERE id = a.entity_id)
                             WHEN 'vlan' THEN (SELECT CONCAT('VLAN ', vlan_id, ' - ', name)
                                               FROM vlans WHERE id = a.entity_id)
                             WHEN 'user' THEN (SELECT username FROM users WHERE id = a.entity_id)
                           END AS target,
                           a.old_value, a.new_value
                    FROM audit_logs a
                    JOIN users u ON u.id = a.user_id
                    WHERE {where_sql}
                    ORDER BY a.id DESC
                    LIMIT :limit OFFSET :offset"""
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        ).mappings().all()

    items = []
    for r in rows:
        d = dict(r)
        d["old_value"] = parse_json(d["old_value"])
        d["new_value"] = parse_json(d["new_value"])
        items.append(d)
    return {"total": total, "page": page, "page_size": page_size, "items": items}