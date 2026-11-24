"""阶段 6 一致性专项：T-C1 ~ T-C14。

验证老人端与子女端基于同一权威库，档案、体征、用药、告警、订单、消息、绑定关系一致；
离线可补传、增量可拉取、冲突不回退、解绑即收回权限。
"""
import pytest

from app import (alerts, auth, bindings, consents, db, errors, family, health,
                 messages, models, offline, orders, profile, sos, sync)


def _elder(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def _family_user(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_FAMILY)


def _bound_setup(conn, elder_phone="13300000001", family_phone="13300000002"):
    elder = _elder(conn, elder_phone)
    family_user = _family_user(conn, family_phone)
    bindings.bind(conn, elder["user_id"], family_user["user_id"])
    profile.upsert_profile(conn, elder["user_id"], {"name": "王阿姨", "age": 68, "allergy": "青霉素"})
    return elder, family_user


# T-C1 档案双向一致
def test_tc1_profile_consistent_between_ends(conn):
    elder, family_user = _bound_setup(conn)
    profile.upsert_profile(conn, elder["user_id"], {"chronic_disease": "高血压", "address": "幸福小区 1 栋"})

    detail = family.get_detail(conn, family_user["user_id"], elder["user_id"])
    assert detail["profile"]["chronic_disease"] == "高血压"
    assert detail["profile"]["allergy"] == "青霉素"
    overview = family.get_overview(conn, family_user["user_id"], elder["user_id"])
    assert overview["name"] == "王阿姨"


# T-C2 体征同步
def test_tc2_vitals_consistent(conn):
    elder, family_user = _bound_setup(conn)
    health.add_vital(conn, elder["user_id"], models.VIT_BP, "122/78", "mmHg")
    health.add_vital(conn, elder["user_id"], models.VIT_HEART, "74", "次/分")

    overview = family.get_overview(conn, family_user["user_id"], elder["user_id"])
    detail = family.get_detail(conn, family_user["user_id"], elder["user_id"])
    assert overview["latest_vitals"][models.VIT_BP]["value"] == "122/78"
    assert len(detail["vitals_history"]) == 2
    elder_history = health.list_vitals(conn, elder["user_id"])
    assert [v["value"] for v in detail["vitals_history"]] == [v["value"] for v in elder_history]


# T-C3 服药状态同步
def test_tc3_medication_status_consistent(conn):
    elder, family_user = _bound_setup(conn)
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    health.mark_medication(conn, med["plan_id"], elder["user_id"], models.MED_TAKEN, "2026-11-24 08:00")

    detail = family.get_detail(conn, family_user["user_id"], elder["user_id"])
    log = detail["medications"][0]["latest_log"]
    assert log["status"] == models.MED_TAKEN
    elder_log = health.latest_medication_status(conn, elder["user_id"])[0]["latest_log"]
    assert log["recorded_at"] == elder_log["recorded_at"]


# T-C4 SOS 告警同步
def test_tc4_sos_alert_consistent(conn):
    elder, family_user = _bound_setup(conn)
    alert = sos.create_sos(conn, elder["user_id"], location="幸福小区", note="头晕", idempotency_key="sos-x")

    alerts_list = alerts.list_alerts(conn, family_user["user_id"])
    assert len(alerts_list) == 1
    assert alerts_list[0]["alert_id"] == alert["alert_id"]
    assert alerts_list[0]["type"] == models.ALERT_SOS
    assert alerts_list[0]["content"] == "头晕"
    assert alerts_list[0]["location"] == "幸福小区"
    assert alerts_list[0]["occurred_at"] == alert["occurred_at"]


# T-C5 规则告警同步
def test_tc5_rule_alerts_sync(conn):
    elder, family_user = _bound_setup(conn)
    high = health.add_vital(conn, elder["user_id"], models.VIT_BP, "195/110", "mmHg")
    alerts.evaluate_vitals(conn, elder["user_id"], high)
    med = health.add_medication(conn, elder["user_id"], "钙片", "2 片", "12:00")
    alerts.raise_missed_med(conn, elder["user_id"], med["plan_id"], "钙片", "2026-11-24 12:00")

    alerts_list = alerts.list_alerts(conn, family_user["user_id"])
    types = {a["type"] for a in alerts_list}
    assert models.ALERT_VITALS_ABNORMAL in types
    assert models.ALERT_MISSED_MED in types


# T-C6 代付订单两端一致
def test_tc6_family_pay_order_consistent(conn):
    elder, family_user = _bound_setup(conn)
    order = orders.create_order(
        conn, elder["user_id"], family_user["user_id"], models.ROLE_FAMILY,
        service_item="陪同就诊", amount=120.0, pay_method=models.PAY_FAMILY,
        idempotency_key="ord-x",
    )
    elder_orders = orders.list_orders_by_elder(conn, elder["user_id"])
    family_orders = orders.list_orders_by_family(conn, family_user["user_id"])
    assert elder_orders[0]["order_id"] == family_orders[0]["order_id"] == order["order_id"]
    assert elder_orders[0]["amount"] == family_orders[0]["amount"] == 120.0
    assert elder_orders[0]["status"] == family_orders[0]["status"]


# T-C7 订单状态同步
def test_tc7_order_status_syncs_both_ends(conn):
    elder, family_user = _bound_setup(conn)
    order = orders.create_order(
        conn, elder["user_id"], family_user["user_id"], models.ROLE_FAMILY,
        service_item="助浴", amount=80.0, pay_method=models.PAY_FAMILY,
    )
    orders.pay_order(conn, family_user["user_id"], order["order_id"])
    orders.advance_order(conn, family_user["user_id"], order["order_id"], models.ORD_COMPLETED)

    elder_view = orders.list_orders_by_elder(conn, elder["user_id"])[0]
    family_view = orders.list_orders_by_family(conn, family_user["user_id"])[0]
    assert elder_view["status"] == family_view["status"] == models.ORD_COMPLETED
    assert elder_view["pay_status"] == family_view["pay_status"] == "paid"


# T-C8 解绑后权限收回
def test_tc8_unbind_revokes_access(conn):
    elder, family_user = _bound_setup(conn)
    sos.create_sos(conn, elder["user_id"], "家中")
    orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                        service_item="助洁", pay_method=models.PAY_SELF)

    bindings.unbind(conn, elder["user_id"], family_user["user_id"])

    with pytest.raises(errors.PermissionError):
        family.get_overview(conn, family_user["user_id"], elder["user_id"])
    assert alerts.list_alerts(conn, family_user["user_id"]) == []
    assert orders.list_orders_by_family(conn, family_user["user_id"]) == []


# T-C9 断网补传成功且不重复
def test_tc9_offline_replay_no_duplicate(conn):
    elder, family_user = _bound_setup(conn)
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    queue = offline.OfflineQueue()

    queue.add("vitals", "create", {"elder_id": elder["user_id"], "type": models.VIT_WEIGHT,
                                   "value": "61", "unit": "kg"}, idempotency_key="off-v1")
    queue.add("medication_logs", "create", {"plan_id": med["plan_id"], "elder_id": elder["user_id"],
                                            "status": models.MED_TAKEN, "planned_at": "2026-11-24 08:00"},
              idempotency_key="off-m1")
    queue.add("messages", "create", {"receiver_id": elder["user_id"], "sender_id": family_user["user_id"],
                                      "type": models.MSG_LETTER, "title": "留言", "body": "注意休息"},
              idempotency_key="off-g1")

    result = sync.replay_queue(conn, queue)
    assert result["failed"] == 0 and result["pending"] == 0

    assert len(health.list_vitals(conn, elder["user_id"])) == 1
    assert health.latest_medication_status(conn, elder["user_id"])[0]["latest_log"]["status"] == models.MED_TAKEN
    assert len(messages.list_messages(conn, elder["user_id"], models.MSG_LETTER)) == 1

    # 再次补传：队列已空，库内不产生重复
    sync.replay_queue(conn, queue)
    assert len(health.list_vitals(conn, elder["user_id"])) == 1
    assert len(messages.list_messages(conn, elder["user_id"])) == 1


# T-C10 离线期间本地副本可读
def test_tc10_offline_copy_readable_before_replay(conn):
    elder, family_user = _bound_setup(conn)
    queue = offline.OfflineQueue()
    queue.add("vitals", "create", {"elder_id": elder["user_id"], "type": models.VIT_HEART,
                                   "value": "76", "unit": "次/分"}, idempotency_key="off-h1")

    pending = queue.pending()
    assert len(pending) == 1
    assert pending[0]["payload"]["value"] == "76"
    # 补传前服务端尚无该体征
    assert health.list_vitals(conn, elder["user_id"]) == []


# T-C11 增量同步只返回新变更
def test_tc11_incremental_pull(conn):
    elder, family_user = _bound_setup(conn)
    baseline = sync.pull_changes(conn)
    before = len(baseline)

    health.add_vital(conn, elder["user_id"], models.VIT_WEIGHT, "63", "kg")
    sos.create_sos(conn, elder["user_id"], "楼下", idempotency_key="off-inc")

    all_changes = sync.pull_changes(conn)
    assert len(all_changes) == before + 2
    future = sync.pull_changes(conn, "2999-01-01T00:00:00+00:00")
    assert future == []


# T-C12 冲突不回退
def test_tc12_conflict_does_not_rollback(conn):
    elder, _ = _bound_setup(conn)
    health.add_vital(conn, elder["user_id"], models.VIT_WEIGHT, "60", "kg")
    health.add_vital(conn, elder["user_id"], models.VIT_WEIGHT, "62", "kg")
    history = health.list_vitals(conn, elder["user_id"], models.VIT_WEIGHT)
    assert len(history) == 2  # 历史记录都保留，不被旧记录覆盖
    assert health.latest_vitals(conn, elder["user_id"])[models.VIT_WEIGHT]["value"] == "62"

    profile.upsert_profile(conn, elder["user_id"], {"name": "王阿姨"})
    profile.upsert_profile(conn, elder["user_id"], {"name": "王秀兰"})
    assert profile.get_profile(conn, elder["user_id"])["name"] == "王秀兰"


# T-C13 已读状态两端一致
def test_tc13_read_status_consistent(conn):
    elder, family_user = _bound_setup(conn)
    alert = sos.create_sos(conn, elder["user_id"], "家中")
    msg = messages.send_message(conn, elder["user_id"], family_user["user_id"],
                                models.MSG_LETTER, "留言", "周末回来")

    alerts.mark_status(conn, family_user["user_id"], alert["alert_id"], models.ALERT_READ)
    messages.mark_read(conn, msg["message_id"])

    server_alert = alerts.list_alerts_unscoped(conn, elder["user_id"])[0]
    assert server_alert["status"] == models.ALERT_READ
    server_msg = messages.list_messages(conn, elder["user_id"])[0]
    assert server_msg["read_status"] == "read"


# T-C14 多家属数据一致
def test_tc14_multiple_families_consistent(conn):
    elder = _elder(conn, "13300000091")
    f1 = _family_user(conn, "13300000092")
    f2 = _family_user(conn, "13300000093")
    bindings.bind(conn, elder["user_id"], f1["user_id"])
    bindings.bind(conn, elder["user_id"], f2["user_id"])
    profile.upsert_profile(conn, elder["user_id"], {"name": "李伯伯", "age": 71})
    health.add_vital(conn, elder["user_id"], models.VIT_GLUCOSE, "6.1", "mmol/L")
    sos.create_sos(conn, elder["user_id"], "公园", idempotency_key="multi-1")
    orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                        service_item="助洁", amount=50, pay_method=models.PAY_SELF)

    o1 = family.get_overview(conn, f1["user_id"], elder["user_id"])
    o2 = family.get_overview(conn, f2["user_id"], elder["user_id"])
    assert o1["name"] == o2["name"] == "李伯伯"
    assert o1["latest_vitals"] == o2["latest_vitals"]
    assert len(alerts.list_alerts(conn, f1["user_id"])) == len(alerts.list_alerts(conn, f2["user_id"])) == 1
    assert len(orders.list_orders_by_family(conn, f1["user_id"])) == \
           len(orders.list_orders_by_family(conn, f2["user_id"])) == 1
