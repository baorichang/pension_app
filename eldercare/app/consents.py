"""隐私授权：定位/麦克风/通知/健康数据，可开启与撤回（阶段 5）。"""
from __future__ import annotations

from app import db, errors, models


def set_consent(conn, user_id: int, elder_id: int | None, item: str, granted: bool) -> dict:
    if item not in models.CONSENT_ITEMS:
        raise errors.ValidationError("授权项无效")
    now = db.utc_now()
    flag = 1 if granted else 0

    existing = conn.execute(
        "SELECT * FROM consents WHERE user_id=? AND elder_id IS ? AND item=?",
        (user_id, elder_id, item),
    ).fetchone()

    if existing is None:
        conn.execute(
            "INSERT INTO consents (user_id, elder_id, item, granted, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, elder_id, item, flag, now, now),
        )
    else:
        conn.execute(
            "UPDATE consents SET granted=?, updated_at=?, version=version+1 WHERE consent_id=?",
            (flag, now, existing["consent_id"]),
        )

    db.record_change(conn, "consents", user_id, elder_id, "update", f"{item}={'授权' if granted else '撤回'}", "system", now)
    conn.commit()
    return get_consent(conn, user_id, elder_id, item)


def get_consent(conn, user_id: int, elder_id: int | None, item: str) -> dict:
    row = conn.execute(
        "SELECT * FROM consents WHERE user_id=? AND elder_id IS ? AND item=?",
        (user_id, elder_id, item),
    ).fetchone()
    if row is None:
        return {"user_id": user_id, "elder_id": elder_id, "item": item, "granted": 0}
    return dict(row)


def is_granted(conn, user_id: int, elder_id: int | None, item: str) -> bool:
    return bool(get_consent(conn, user_id, elder_id, item)["granted"])


def list_consents(conn, user_id: int, elder_id: int | None = None) -> list[dict]:
    if elder_id is None:
        rows = conn.execute("SELECT * FROM consents WHERE user_id=?", (user_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM consents WHERE user_id=? AND elder_id IS ?", (user_id, elder_id)
        ).fetchall()
    return [dict(r) for r in rows]
