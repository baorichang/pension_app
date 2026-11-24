"""订单：创建、本人支付/家属代付、服务端状态机与两端同源查询（阶段 4）。

订单只存一份于权威库；老人端"我的订单"与子女端"代付订单"按同一 order_id 读取。
状态只能由服务端状态机流转，调用方提交动作，不能直接改写状态。
"""
from __future__ import annotations

from app import bindings, db, errors, models


def _get_user(conn, user_id: int):
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("下单用户不存在")
    return row


def _assert_order_visible(conn, order: dict, user_id: int) -> None:
    if order["elder_id"] == user_id:
        return
    bindings.assert_can_access(conn, user_id, order["elder_id"])


def create_order(conn, elder_id: int, orderer_id: int, orderer_role: str,
                 service_item: str, resource_id: int | None = None,
                 appointment_time: str = "", address: str = "", amount: float = 0.0,
                 pay_method: str = models.PAY_SELF, idempotency_key: str | None = None) -> dict:
    if orderer_role not in models.ROLES:
        raise errors.ValidationError("下单人角色无效")
    if pay_method not in models.PAY_METHODS:
        raise errors.ValidationError("支付方式无效")
    if not service_item or not service_item.strip():
        raise errors.ValidationError("服务项目不能为空")
    if amount < 0:
        raise errors.ValidationError("金额不能为负")

    elder = _get_user(conn, elder_id)
    if elder["role"] != models.ROLE_ELDER:
        raise errors.ValidationError("被服务人必须是老人角色")

    if pay_method == models.PAY_SELF:
        if orderer_role != models.ROLE_ELDER or orderer_id != elder_id:
            raise errors.ValidationError("本人支付只能由老人本人下单")
    else:
        if orderer_role != models.ROLE_FAMILY:
            raise errors.ValidationError("代付只能由家属下单")
        bindings.assert_can_access(conn, orderer_id, elder_id)

    now = db.utc_now()
    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM orders WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO orders (elder_id, orderer_id, orderer_role, resource_id, service_item, "
        "appointment_time, address, amount, pay_method, status, pay_status, idempotency_key, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (elder_id, orderer_id, orderer_role, resource_id, service_item.strip(), appointment_time,
         address, amount, pay_method, models.ORD_PENDING_PAY, "unpaid", idempotency_key, now, now),
    )
    order_id = cur.lastrowid
    db.record_change(conn, "orders", order_id, elder_id, "create", f"下单 {service_item.strip()}", orderer_role, now)
    conn.commit()
    return get_order(conn, order_id)


def get_order(conn, order_id: int) -> dict:
    row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if row is None:
        raise errors.NotFoundError("订单不存在")
    return dict(row)


def pay_order(conn, orderer_id: int, order_id: int) -> dict:
    """支付动作：待付款 → 进行中，支付状态置为已付。"""
    order = get_order(conn, order_id)
    _assert_order_visible(conn, order, orderer_id)
    if order["status"] != models.ORD_PENDING_PAY:
        raise errors.ConflictError("当前订单状态不可支付")
    return _transition(conn, order, models.ORD_IN_PROGRESS, pay_status="paid")


def advance_order(conn, operator_id: int, order_id: int, target_status: str) -> dict:
    order = get_order(conn, order_id)
    _assert_order_visible(conn, order, operator_id)
    return _transition(conn, order, target_status)


def _transition(conn, order: dict, target_status: str, pay_status: str | None = None) -> dict:
    current = order["status"]
    if target_status not in models.ORDER_STATUSES:
        raise errors.ValidationError("目标订单状态无效")
    if target_status not in models.ORDER_TRANSITIONS[current]:
        raise errors.ConflictError(f"订单状态不允许从 {current} 流转到 {target_status}")

    now = db.utc_now()
    pay_status = pay_status or order["pay_status"]
    conn.execute(
        "UPDATE orders SET status=?, pay_status=?, updated_at=?, version=version+1 WHERE order_id=?",
        (target_status, pay_status, now, order["order_id"]),
    )
    db.record_change(conn, "orders", order["order_id"], order["elder_id"], "update",
                     f"订单状态 {target_status}", "system", now)
    conn.commit()
    return get_order(conn, order["order_id"])


def list_orders_by_elder(conn, elder_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM orders WHERE elder_id=? ORDER BY created_at DESC", (elder_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_orders_by_family(conn, family_id: int) -> list[dict]:
    elders = bindings.list_elders_of_family(conn, family_id)
    if not elders:
        return []
    placeholders = ",".join("?" for _ in elders)
    rows = conn.execute(
        f"SELECT * FROM orders WHERE elder_id IN ({placeholders}) ORDER BY created_at DESC",
        tuple(elders),
    ).fetchall()
    return [dict(r) for r in rows]
