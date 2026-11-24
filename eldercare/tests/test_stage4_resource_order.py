"""阶段 4 测试：服务资源、订单状态机与两端同源订单。"""
import pytest

from app import (auth, bindings, errors, models, orders, resources)


def _elder(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def _family_user(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_FAMILY)


def test_resources_filter_by_category(conn):
    resources.add_resource(conn, models.RES_HOME, "助浴服务", price_range="¥80/次", location="家中")
    resources.add_resource(conn, models.RES_COMMUNITY, "书法课", event_time="周六 15:00")
    resources.add_resource(conn, models.RES_ORG, "康乐养老院", price_range="面议")

    home = resources.list_resources(conn, models.RES_HOME)
    assert len(home) == 1 and home[0]["name"] == "助浴服务"
    assert len(resources.list_resources(conn, models.RES_COMMUNITY)) == 1
    assert len(resources.list_resources(conn)) == 3


def test_elder_self_order_created_pending(conn):
    elder = _elder(conn, "13500000001")
    order = orders.create_order(
        conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
        service_item="居家助洁", appointment_time="2026-11-25 10:00",
        address="幸福小区 1 栋", amount=60.0, pay_method=models.PAY_SELF,
    )
    assert order["status"] == models.ORD_PENDING_PAY
    assert order["pay_status"] == "unpaid"
    assert order["elder_id"] == elder["user_id"]


def test_family_pay_order_visible_to_both_ends(conn):
    elder = _elder(conn, "13500000011")
    family_user = _family_user(conn, "13500000012")
    bindings.bind(conn, elder["user_id"], family_user["user_id"])

    order = orders.create_order(
        conn, elder["user_id"], family_user["user_id"], models.ROLE_FAMILY,
        service_item="陪同就诊", amount=120.0, pay_method=models.PAY_FAMILY,
        idempotency_key="order-1",
    )
    elder_orders = orders.list_orders_by_elder(conn, elder["user_id"])
    family_orders = orders.list_orders_by_family(conn, family_user["user_id"])
    assert len(elder_orders) == 1
    assert len(family_orders) == 1
    assert elder_orders[0]["order_id"] == family_orders[0]["order_id"] == order["order_id"]
    assert elder_orders[0]["amount"] == family_orders[0]["amount"] == 120.0


def test_unbound_family_cannot_pay_order(conn):
    elder = _elder(conn, "13500000021")
    stranger = _family_user(conn, "13500000022")
    with pytest.raises(errors.PermissionError):
        orders.create_order(
            conn, elder["user_id"], stranger["user_id"], models.ROLE_FAMILY,
            service_item="助浴", pay_method=models.PAY_FAMILY,
        )


def test_self_pay_cannot_be_placed_by_family(conn):
    elder = _elder(conn, "13500000031")
    family_user = _family_user(conn, "13500000032")
    bindings.bind(conn, elder["user_id"], family_user["user_id"])
    with pytest.raises(errors.ValidationError):
        orders.create_order(
            conn, elder["user_id"], family_user["user_id"], models.ROLE_FAMILY,
            service_item="助浴", pay_method=models.PAY_SELF,
        )


def test_order_idempotent_key_prevents_duplicate(conn):
    elder = _elder(conn, "13500000041")
    o1 = orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                             service_item="理发", amount=30, idempotency_key="dup-1")
    o2 = orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                             service_item="理发", amount=30, idempotency_key="dup-1")
    assert o1["order_id"] == o2["order_id"]
    assert len(orders.list_orders_by_elder(conn, elder["user_id"])) == 1


def test_pay_then_complete_state_machine(conn):
    elder = _elder(conn, "13500000051")
    order = orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                                 service_item="助浴", amount=80, pay_method=models.PAY_SELF)
    paid = orders.pay_order(conn, elder["user_id"], order["order_id"])
    assert paid["status"] == models.ORD_IN_PROGRESS
    assert paid["pay_status"] == "paid"

    done = orders.advance_order(conn, elder["user_id"], order["order_id"], models.ORD_COMPLETED)
    assert done["status"] == models.ORD_COMPLETED


def test_illegal_state_transition_rejected(conn):
    elder = _elder(conn, "13500000061")
    order = orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                                 service_item="助洁", amount=50, pay_method=models.PAY_SELF)
    with pytest.raises(errors.ConflictError):
        orders.advance_order(conn, elder["user_id"], order["order_id"], models.ORD_COMPLETED)


def test_family_only_sees_bound_elder_orders(conn):
    elder_a = _elder(conn, "13500000071")
    elder_b = _elder(conn, "13500000072")
    family_user = _family_user(conn, "13500000073")
    bindings.bind(conn, elder_a["user_id"], family_user["user_id"])
    orders.create_order(conn, elder_a["user_id"], elder_a["user_id"], models.ROLE_ELDER,
                        service_item="助洁", pay_method=models.PAY_SELF)
    orders.create_order(conn, elder_b["user_id"], elder_b["user_id"], models.ROLE_ELDER,
                        service_item="助浴", pay_method=models.PAY_SELF)

    family_orders = orders.list_orders_by_family(conn, family_user["user_id"])
    assert all(o["elder_id"] == elder_a["user_id"] for o in family_orders)
    assert len(family_orders) == 1
