"""家属视角聚合：父母概览、老人详情（阶段 3）。

所有接口先做绑定鉴权，再从权威库聚合老人端写入的同源数据；
家属端不维护独立副本。
"""
from __future__ import annotations

from app import alerts, bindings, health, models, orders, profile


def _location_of(alerts_list: list[dict]) -> str:
    for a in alerts_list:
        if a.get("location"):
            return a["location"]
    return ""


def _build_overview(conn, elder_id: int) -> dict:
    prof = profile.get_profile(conn, elder_id) or {}
    latest = health.latest_vitals(conn, elder_id)
    elder_alerts = alerts.list_alerts_unscoped(conn, elder_id)
    unread = [a for a in elder_alerts if a["status"] == models.ALERT_UNREAD]
    abnormal_types = {models.ALERT_SOS, models.ALERT_VITALS_ABNORMAL}
    alert_flag = any(a["type"] in abnormal_types for a in unread)

    return {
        "elder_id": elder_id,
        "name": prof.get("name"),
        "age": prof.get("age"),
        "gender": prof.get("gender"),
        "latest_vitals": latest,
        "location": _location_of(elder_alerts),
        "alert_flag": alert_flag,
        "unread_count": len(unread),
    }


def list_overviews(conn, family_id: int) -> list[dict]:
    elders = bindings.list_elders_of_family(conn, family_id)
    return [_build_overview(conn, e) for e in elders]


def get_overview(conn, family_id: int, elder_id: int) -> dict:
    bindings.assert_can_access(conn, family_id, elder_id)
    return _build_overview(conn, elder_id)


def get_detail(conn, family_id: int, elder_id: int) -> dict:
    bindings.assert_can_access(conn, family_id, elder_id)
    prof = profile.get_profile(conn, elder_id)
    vitals_history = health.list_vitals(conn, elder_id)
    medications = health.latest_medication_status(conn, elder_id)
    elder_alerts = alerts.list_alerts_unscoped(conn, elder_id)

    return {
        "elder_id": elder_id,
        "profile": prof,
        "vitals_history": vitals_history,
        "medications": medications,
        "alerts": elder_alerts,
        "service_records": orders.list_orders_by_elder(conn, elder_id),
    }
