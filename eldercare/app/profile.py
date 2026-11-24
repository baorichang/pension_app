"""老人健康档案（阶段 2）。

档案为可覆盖型数据：服务端最新为准（last-write-wins），更新版本号与时间戳。
"""
from __future__ import annotations

from app import db, errors, models

PROFILE_FIELDS = (
    "name", "gender", "age", "blood_type", "chronic_disease", "history",
    "allergy", "common_meds", "emergency_contact", "address",
)


def _require_elder(conn, elder_id: int) -> None:
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (elder_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("老人账号不存在")
    if row["role"] != models.ROLE_ELDER:
        raise errors.ValidationError("该账号不是老人角色")


def get_profile(conn, elder_id: int):
    row = conn.execute("SELECT * FROM elder_profile WHERE elder_id=?", (elder_id,)).fetchone()
    return dict(row) if row else None


def upsert_profile(conn, elder_id: int, data: dict) -> dict:
    _require_elder(conn, elder_id)
    now = db.utc_now()
    fields = {k: v for k, v in data.items() if k in PROFILE_FIELDS}

    existing = conn.execute("SELECT * FROM elder_profile WHERE elder_id=?", (elder_id,)).fetchone()
    if existing is None:
        cols = ["elder_id", "created_at", "updated_at", *fields.keys()]
        vals = [elder_id, now, now, *fields.values()]
        placeholders = ",".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO elder_profile ({','.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        profile_id = conn.execute("SELECT profile_id FROM elder_profile WHERE elder_id=?", (elder_id,)).fetchone()["profile_id"]
        op = "create"
    else:
        if fields:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            conn.execute(
                f"UPDATE elder_profile SET {set_clause}, updated_at=?, version=version+1 WHERE elder_id=?",
                (*fields.values(), now, elder_id),
            )
        profile_id = existing["profile_id"]
        op = "update"

    db.record_change(conn, "elder_profile", profile_id, elder_id, op, "档案更新", "elder", now)
    conn.commit()
    return get_profile(conn, elder_id)
