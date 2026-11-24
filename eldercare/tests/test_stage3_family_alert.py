"""阶段 3 测试：家属概览/详情、告警规则与已读同步。"""
import pytest

from app import (alerts, auth, bindings, errors, family, health, models, profile, sos)


def _elder(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def _family_user(conn, phone):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_FAMILY)


def _setup(conn):
    elder = _elder(conn, "13600000001")
    family_user = _family_user(conn, "13600000002")
    bindings.bind(conn, elder["user_id"], family_user["user_id"])
    profile.upsert_profile(conn, elder["user_id"], {"name": "王阿姨", "age": 68})
    return elder, family_user


def test_overview_shows_bound_elder_with_vitals_and_location(conn):
    elder, family_user = _setup(conn)
    health.add_vital(conn, elder["user_id"], models.VIT_BP, "120/80", "mmHg")
    sos.create_sos(conn, elder["user_id"], location="幸福小区 1 栋")

    overview = family.get_overview(conn, family_user["user_id"], elder["user_id"])
    assert overview["name"] == "王阿姨"
    assert overview["latest_vitals"][models.VIT_BP]["value"] == "120/80"
    assert overview["location"] == "幸福小区 1 栋"
    assert overview["alert_flag"] is True


def test_overview_denied_without_bind(conn):
    elder = _elder(conn, "13600000011")
    stranger = _family_user(conn, "13600000012")
    with pytest.raises(errors.PermissionError):
        family.get_overview(conn, stranger["user_id"], elder["user_id"])


def test_detail_contains_profile_vitals_meds_alerts(conn):
    elder, family_user = _setup(conn)
    health.add_vital(conn, elder["user_id"], models.VIT_HEART, "72", "次/分")
    med = health.add_medication(conn, elder["user_id"], "钙片", "2 片", "12:00")
    health.mark_medication(conn, med["plan_id"], elder["user_id"], models.MED_TAKEN, "2026-11-24 12:00")

    detail = family.get_detail(conn, family_user["user_id"], elder["user_id"])
    assert detail["profile"]["name"] == "王阿姨"
    assert len(detail["vitals_history"]) == 1
    assert detail["medications"][0]["name"] == "钙片"
    assert isinstance(detail["alerts"], list)


def test_sos_alert_visible_to_family_consistently(conn):
    elder, family_user = _setup(conn)
    alert = sos.create_sos(conn, elder["user_id"], location="家中", note="需要帮助")
    alerts_list = alerts.list_alerts(conn, family_user["user_id"])
    assert len(alerts_list) == 1
    assert alerts_list[0]["alert_id"] == alert["alert_id"]
    assert alerts_list[0]["content"] == "需要帮助"
    assert alerts_list[0]["location"] == "家中"


def test_vitals_abnormal_rule_triggers_alert(conn):
    elder, family_user = _setup(conn)
    high = health.add_vital(conn, elder["user_id"], models.VIT_BP, "190/105", "mmHg")
    alert = alerts.evaluate_vitals(conn, elder["user_id"], high)
    assert alert is not None
    assert alert["type"] == models.ALERT_VITALS_ABNORMAL

    normal = health.add_vital(conn, elder["user_id"], models.VIT_HEART, "70", "次/分")
    assert alerts.evaluate_vitals(conn, elder["user_id"], normal) is None


def test_missed_med_alert_generated(conn):
    elder, family_user = _setup(conn)
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    alert = alerts.raise_missed_med(conn, elder["user_id"], med["plan_id"], "降压药", "2026-11-24 08:00")
    assert alert["type"] == models.ALERT_MISSED_MED
    assert "降压药" in alert["content"]


def test_alert_read_status_syncs_back(conn):
    elder, family_user = _setup(conn)
    alert = sos.create_sos(conn, elder["user_id"], "家中")
    updated = alerts.mark_status(conn, family_user["user_id"], alert["alert_id"], models.ALERT_READ)
    assert updated["status"] == models.ALERT_READ
    again = alerts.list_alerts(conn, family_user["user_id"])[0]
    assert again["status"] == models.ALERT_READ


def test_family_cannot_read_unbound_elder_alerts(conn):
    elder = _elder(conn, "13600000021")
    family_user = _family_user(conn, "13600000022")
    sos.create_sos(conn, elder["user_id"], "家中")
    assert alerts.list_alerts(conn, family_user["user_id"]) == []
