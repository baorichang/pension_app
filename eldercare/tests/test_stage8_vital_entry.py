"""阶段 8（问题 2）：健康页按体征类型点击录入，支持按类型查询。"""
from __future__ import annotations

from app import auth, health, models


def _elder(conn, phone="13722220002"):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def test_record_by_type_and_filter_same_type(conn):
    elder = _elder(conn)
    eid = elder["user_id"]
    health.add_vital(conn, eid, models.VIT_BP, "122/78", "mmHg")
    health.add_vital(conn, eid, models.VIT_HEART, "76", "次/分")
    health.add_vital(conn, eid, models.VIT_WEIGHT, "60", "kg")

    heart = health.list_vitals(conn, eid, models.VIT_HEART)
    assert len(heart) == 1
    assert heart[0]["type"] == models.VIT_HEART
    assert heart[0]["value"] == "76"

    bp = health.list_vitals(conn, eid, models.VIT_BP)
    assert all(v["type"] == models.VIT_BP for v in bp)


def test_latest_vitals_keep_per_type(conn):
    elder = _elder(conn)
    eid = elder["user_id"]
    health.add_vital(conn, eid, models.VIT_HEART, "70", "次/分")
    health.add_vital(conn, eid, models.VIT_HEART, "82", "次/分")
    latest = health.latest_vitals(conn, eid)
    assert latest[models.VIT_HEART]["value"] == "82"
    assert models.VIT_BP not in latest


def test_filter_unknown_type_returns_empty(conn):
    elder = _elder(conn)
    eid = elder["user_id"]
    health.add_vital(conn, eid, models.VIT_BP, "122/78", "mmHg")
    assert health.list_vitals(conn, eid, models.VIT_GLUCOSE) == []
