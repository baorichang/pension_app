"""紧急求助 SOS 与安全开关（阶段 2）。

发起求助即生成一条 SOS 告警记录，同步推送/拉取给已绑定家属；
求助提交凭幂等键去重，重试不产生重复告警。
"""
from __future__ import annotations

import json

from app import db, errors, models


def _require_elder(conn, elder_id: int) -> None:
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (elder_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("老人账号不存在")
    if row["role"] != models.ROLE_ELDER:
        raise errors.ValidationError("该账号不是老人角色")


def create_sos(conn, elder_id: int, location: str = "", note: str = "",
               idempotency_key: str | None = None) -> dict:
    _require_elder(conn, elder_id)
    now = db.utc_now()

    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM alerts WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO alerts (elder_id, type, content, location, occurred_at, status, "
        "idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (elder_id, models.ALERT_SOS, note, location, now, models.ALERT_UNREAD,
         idempotency_key, now, now),
    )
    alert_id = cur.lastrowid
    db.record_change(conn, "alerts", alert_id, elder_id, "create", "发起 SOS 求助", "elder", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchone())


def list_sos_records(conn, elder_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM alerts WHERE elder_id=? AND type=? ORDER BY occurred_at DESC",
        (elder_id, models.ALERT_SOS),
    ).fetchall()
    return [dict(r) for r in rows]


def get_sos_settings(conn, elder_id: int) -> dict:
    row = conn.execute("SELECT * FROM sos_settings WHERE elder_id=?", (elder_id,)).fetchone()
    if row is None:
        return {"elder_id": elder_id, "fall_detection": 1, "geofence": 1, "idle_reminder": 0}
    return dict(row)


def set_sos_settings(conn, elder_id: int, fall_detection: int | None = None,
                     geofence: int | None = None, idle_reminder: int | None = None) -> dict:
    now = db.utc_now()
    current = get_sos_settings(conn, elder_id)
    fall = current["fall_detection"] if fall_detection is None else int(fall_detection)
    geo = current["geofence"] if geofence is None else int(geofence)
    idle = current["idle_reminder"] if idle_reminder is None else int(idle_reminder)

    conn.execute(
        "INSERT INTO sos_settings (elder_id, fall_detection, geofence, idle_reminder, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(elder_id) DO UPDATE SET fall_detection=?, geofence=?, idle_reminder=?, updated_at=?",
        (elder_id, fall, geo, idle, now, fall, geo, idle, now),
    )
    db.record_change(conn, "sos_settings", elder_id, elder_id, "update", "安全开关设置", "elder", now)
    conn.commit()
    return get_sos_settings(conn, elder_id)


def set_emergency_contact(conn, elder_id: int, contact: str) -> dict:
    """紧急联系人写入档案（姓名+电话，占位 JSON 或文本）。"""
    from app import profile as profile_module

    return profile_module.upsert_profile(conn, elder_id, {"emergency_contact": contact})


def get_emergency_contacts(conn, elder_id: int) -> list[dict]:
    profile = profile_module_get(conn, elder_id)
    raw = (profile or {}).get("emergency_contact") or ""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return [{"name": "紧急联系人", "phone": raw}]


def profile_module_get(conn, elder_id: int):
    from app import profile as profile_module
    return profile_module.get_profile(conn, elder_id)
