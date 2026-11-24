"""两端同步：增量拉取、离线队列补传与一致性规则（阶段 6）。

- 权威库为唯一数据源；客户端先落本地队列，联网后按序补传。
- 增量拉取基于 change_log 的 changed_at 游标，只返回新变更。
- 覆盖型数据（档案/设置）last-write-wins；追加型数据（体征/服药/告警/消息）只追加不回退。
- 写操作携带幂等键，补传重试不产生重复记录。
"""
from __future__ import annotations

from typing import Callable

from app import health, messages, sos


def pull_changes(conn, since: str = "") -> list[dict]:
    """拉取自 since 时间戳之后的全部实体变更，按发生顺序返回。"""
    if since:
        rows = conn.execute(
            "SELECT * FROM change_log WHERE changed_at > ? ORDER BY changed_at ASC, log_id ASC",
            (since,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM change_log ORDER BY changed_at ASC, log_id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def default_handlers() -> dict[str, Callable]:
    """队列实体类型 → 服务端补传方法映射。"""
    return {
        "vitals": lambda conn, p, key: health.add_vital(
            conn, p["elder_id"], p["type"], p["value"], p.get("unit", ""),
            p.get("measured_at"), idempotency_key=key,
        ),
        "medication_logs": lambda conn, p, key: health.mark_medication(
            conn, p["plan_id"], p["elder_id"], p["status"], p["planned_at"],
            idempotency_key=key,
        ),
        "messages": lambda conn, p, key: messages.send_message(
            conn, p["receiver_id"], p.get("sender_id"), p["type"], p["title"],
            p.get("body", ""), p.get("ref_type", ""), p.get("ref_id"),
            idempotency_key=key,
        ),
        "alerts": lambda conn, p, key: sos.create_sos(
            conn, p["elder_id"], p.get("location", ""), p.get("note", ""),
            idempotency_key=key,
        ),
    }


def replay_queue(conn, queue, handlers: dict[str, Callable] | None = None) -> dict:
    """按本地队列顺序补传；成功出队，失败保留并计数。返回成功/失败统计。"""
    handlers = handlers or default_handlers()
    done, failed = 0, 0
    for item in queue.pending():
        handler = handlers.get(item["entity_type"])
        if handler is None:
            queue.mark_failed(item["key"])
            failed += 1
            continue
        try:
            handler(conn, item["payload"], item["idempotency_key"])
            queue.mark_done(item["key"])
            done += 1
        except Exception:
            queue.mark_failed(item["key"])
            failed += 1
    return {"done": done, "failed": failed, "pending": len(queue)}
