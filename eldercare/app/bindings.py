"""亲属绑定与访问权限（阶段 1）。

关系为多对多：一名老人可绑定多名家属，一名家属可绑定多名老人。
绑定即授权，解绑即收回；所有跨端读取家属视角数据前必须通过 can_access 校验。
"""
from __future__ import annotations

from app import db, errors, models


def _require_role(conn, user_id: int, role: str) -> None:
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("用户不存在")
    if row["role"] != role:
        raise errors.ValidationError(f"用户 {user_id} 不是{('老人' if role == models.ROLE_ELDER else '家属')}角色")


def bind(conn, elder_id: int, family_id: int) -> dict:
    _require_role(conn, elder_id, models.ROLE_ELDER)
    _require_role(conn, family_id, models.ROLE_FAMILY)

    now = db.utc_now()
    existing = conn.execute(
        "SELECT * FROM family_relations WHERE elder_id=? AND family_id=?",
        (elder_id, family_id),
    ).fetchone()

    if existing is not None:
        if existing["status"] == models.REL_ACTIVE:
            return {"relation_id": existing["relation_id"], "status": models.REL_ACTIVE}
        # 解绑后重新绑定：恢复 active
        conn.execute(
            "UPDATE family_relations SET status=?, updated_at=?, version=version+1 WHERE relation_id=?",
            (models.REL_ACTIVE, now, existing["relation_id"]),
        )
        relation_id = existing["relation_id"]
    else:
        cur = conn.execute(
            "INSERT INTO family_relations (elder_id, family_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (elder_id, family_id, models.REL_ACTIVE, now, now),
        )
        relation_id = cur.lastrowid

    db.record_change(conn, "family_relations", relation_id, elder_id, "bind", "家属绑定老人", "family", now)
    conn.commit()
    return {"relation_id": relation_id, "status": models.REL_ACTIVE}


def unbind(conn, elder_id: int, family_id: int) -> dict:
    now = db.utc_now()
    cur = conn.execute(
        "UPDATE family_relations SET status=?, updated_at=?, version=version+1 "
        "WHERE elder_id=? AND family_id=?",
        (models.REL_UNBOUND, now, elder_id, family_id),
    )
    if cur.rowcount == 0:
        raise errors.NotFoundError("绑定关系不存在")
    db.record_change(conn, "family_relations", 0, elder_id, "unbind", "解除绑定，收回权限", "family", now)
    conn.commit()
    return {"elder_id": elder_id, "family_id": family_id, "status": models.REL_UNBOUND}


def active_relation(conn, elder_id: int, family_id: int):
    return conn.execute(
        "SELECT * FROM family_relations WHERE elder_id=? AND family_id=? AND status=?",
        (elder_id, family_id, models.REL_ACTIVE),
    ).fetchone()


def can_access(conn, family_id: int, elder_id: int) -> bool:
    return active_relation(conn, elder_id, family_id) is not None


def assert_can_access(conn, family_id: int, elder_id: int) -> None:
    if not can_access(conn, family_id, elder_id):
        raise errors.PermissionError("未绑定或已解绑，无权查看该老人数据")


def list_elders_of_family(conn, family_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT elder_id FROM family_relations WHERE family_id=? AND status=?",
        (family_id, models.REL_ACTIVE),
    ).fetchall()
    return [r["elder_id"] for r in rows]


def list_family_of_elder(conn, elder_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT family_id FROM family_relations WHERE elder_id=? AND status=?",
        (elder_id, models.REL_ACTIVE),
    ).fetchall()
    return [r["family_id"] for r in rows]
