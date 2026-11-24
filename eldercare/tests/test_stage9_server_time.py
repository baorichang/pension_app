"""阶段 9（问题 3）：所有操作时间戳取服务端当时系统时间，子女端操作同样适用。"""
from __future__ import annotations

from app import (alerts, auth, bindings, db, health, models, orders, sos)


def _setup(conn):
    elder = auth.login(conn, "13733330003", auth.DEV_FIXED_CODE, models.ROLE_ELDER)
    fam = auth.login(conn, "13733330004", auth.DEV_FIXED_CODE, models.ROLE_FAMILY)
    bindings.bind(conn, elder["user_id"], fam["user_id"])
    return elder, fam


def test_family_order_and_pay_use_server_time(conn):
    elder, fam = _setup(conn)
    before = db.utc_now()
    order = orders.create_order(
        conn, elder["user_id"], fam["user_id"], models.ROLE_FAMILY,
        "陪诊服务", amount=100.0, pay_method=models.PAY_FAMILY,
    )
    assert order["created_at"] >= before
    paid = orders.pay_order(conn, fam["user_id"], order["order_id"])
    assert paid["updated_at"] >= order["created_at"]
    # 子女端代付订单与老人端同源，时间戳一致
    elder_orders = orders.list_orders_by_elder(conn, elder["user_id"])
    same = next(o for o in elder_orders if o["order_id"] == order["order_id"])
    assert same["created_at"] == order["created_at"]
    assert same["updated_at"] == paid["updated_at"]


def test_alert_read_uses_server_time(conn):
    elder, fam = _setup(conn)
    alert = sos.create_sos(conn, elder["user_id"], "家中", "需要帮助")
    before = db.utc_now()
    updated = alerts.mark_status(conn, fam["user_id"], alert["alert_id"], models.ALERT_READ)
    assert updated["updated_at"] >= before
    assert updated["updated_at"] >= alert["created_at"]


def test_medication_recorded_at_is_server_time_not_client_planned_at(conn):
    elder, _ = _setup(conn)
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    before = db.utc_now()
    log = health.mark_medication(
        conn, med["plan_id"], elder["user_id"], models.MED_TAKEN,
        planned_at="2000-01-01T00:00:00+00:00",
    )
    # 操作时间 recorded_at 必须是服务端当前时间，而不是客户端传入的旧计划时间
    assert log["recorded_at"] >= before
    assert log["recorded_at"] != log["planned_at"]


def test_vital_timestamp_uses_server_time(conn):
    elder, _ = _setup(conn)
    before = db.utc_now()
    vital = health.add_vital(conn, elder["user_id"], models.VIT_HEART, "76", "次/分")
    assert vital["measured_at"] >= before
    assert vital["created_at"] >= before
