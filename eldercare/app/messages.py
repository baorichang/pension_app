"""消息通知：通知/提醒/留言/公告与已读状态（阶段 5）。"""
from __future__ import annotations

from app import db, errors, models


def send_message(conn, receiver_id: int, sender_id: int | None, mtype: str,
                 title: str, body: str = "", ref_type: str = "", ref_id: int | None = None,
                 idempotency_key: str | None = None) -> dict:
    if mtype not in models.MESSAGE_TYPES:
        raise errors.ValidationError("消息类型无效")
    if not title or not title.strip():
        raise errors.ValidationError("消息标题不能为空")
    now = db.utc_now()

    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM messages WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO messages (receiver_id, sender_id, type, title, body, ref_type, ref_id, "
        "read_status, idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (receiver_id, sender_id, mtype, title.strip(), body, ref_type, ref_id,
         "unread", idempotency_key, now, now),
    )
    message_id = cur.lastrowid
    db.record_change(conn, "messages", message_id, None, "create", title.strip(), "system", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone())


def list_messages(conn, receiver_id: int, mtype: str | None = None) -> list[dict]:
    if mtype:
        if mtype not in models.MESSAGE_TYPES:
            raise errors.ValidationError("消息类型无效")
        rows = conn.execute(
            "SELECT * FROM messages WHERE receiver_id=? AND type=? ORDER BY created_at DESC",
            (receiver_id, mtype),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE receiver_id=? ORDER BY created_at DESC", (receiver_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_read(conn, message_id: int) -> dict:
    msg = conn.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone()
    if msg is None:
        raise errors.NotFoundError("消息不存在")
    now = db.utc_now()
    conn.execute(
        "UPDATE messages SET read_status='read', updated_at=?, version=version+1 WHERE message_id=?",
        (now, message_id),
    )
    db.record_change(conn, "messages", message_id, None, "update", "消息已读", "system", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM messages WHERE message_id=?", (message_id,)).fetchone())
