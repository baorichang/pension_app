"""服务资源：居家上门 / 社区服务 / 养老机构（阶段 4，两端只读）。"""
from __future__ import annotations

from app import db, errors, models


def add_resource(conn, category: str, name: str, description: str = "",
                 duration_or_quota: str = "", price_range: str = "", location: str = "",
                 event_time: str = "", contact: str = "") -> dict:
    if category not in models.RESOURCE_CATEGORIES:
        raise errors.ValidationError("资源分类无效")
    if not name or not name.strip():
        raise errors.ValidationError("资源名称不能为空")
    now = db.utc_now()
    cur = conn.execute(
        "INSERT INTO service_resources (category, name, description, duration_or_quota, "
        "price_range, location, event_time, contact, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (category, name.strip(), description, duration_or_quota, price_range,
         location, event_time, contact, now, now),
    )
    resource_id = cur.lastrowid
    db.record_change(conn, "service_resources", resource_id, None, "create", name.strip(), "system", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM service_resources WHERE resource_id=?", (resource_id,)).fetchone())


def list_resources(conn, category: str | None = None) -> list[dict]:
    if category:
        if category not in models.RESOURCE_CATEGORIES:
            raise errors.ValidationError("资源分类无效")
        rows = conn.execute(
            "SELECT * FROM service_resources WHERE category=? ORDER BY resource_id", (category,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM service_resources ORDER BY resource_id").fetchall()
    return [dict(r) for r in rows]


def get_resource(conn, resource_id: int) -> dict:
    row = conn.execute("SELECT * FROM service_resources WHERE resource_id=?", (resource_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("服务资源不存在")
    return dict(row)
