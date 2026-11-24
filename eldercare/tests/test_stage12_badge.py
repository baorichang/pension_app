"""阶段 12（问题 6）：未读消息 / 未处理告警导航角标计数。"""
from __future__ import annotations

import pathlib

from app import alerts, auth, bindings, messages, models, sos

HTML = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "index.html"


def _setup(conn):
    elder = auth.login(conn, "13744440005", auth.DEV_FIXED_CODE, models.ROLE_ELDER)
    fam = auth.login(conn, "13744440006", auth.DEV_FIXED_CODE, models.ROLE_FAMILY)
    bindings.bind(conn, elder["user_id"], fam["user_id"])
    return elder, fam


def test_unread_message_count(conn):
    elder, _ = _setup(conn)
    messages.send_message(conn, elder["user_id"], None, models.MSG_NOTICE, "服药提醒")
    messages.send_message(conn, elder["user_id"], None, models.MSG_LETTER, "子女留言")
    assert messages.count_unread(conn, elder["user_id"]) == 2

    first = messages.list_messages(conn, elder["user_id"])[0]
    messages.mark_read(conn, first["message_id"])
    assert messages.count_unread(conn, elder["user_id"]) == 1


def test_unread_alert_count_for_family(conn):
    elder, fam = _setup(conn)
    sos.create_sos(conn, elder["user_id"], "家中", "求助一")
    alerts.raise_alert(conn, elder["user_id"], models.ALERT_VITALS_ABNORMAL, "血压异常")
    assert alerts.count_unread(conn, fam["user_id"]) == 2

    alert = alerts.list_alerts(conn, fam["user_id"])[0]
    alerts.mark_status(conn, fam["user_id"], alert["alert_id"], models.ALERT_READ)
    assert alerts.count_unread(conn, fam["user_id"]) == 1


def test_family_without_bindings_has_zero_alert_count(conn):
    fam = auth.login(conn, "13744440007", auth.DEV_FIXED_CODE, models.ROLE_FAMILY)
    assert alerts.count_unread(conn, fam["user_id"]) == 0


def test_badge_ui_present():
    html = HTML.read_text(encoding="utf-8")
    for token in (
        'class="badge"',
        "/api/messages/unread-count",
        "/api/family/alerts/unread-count",
        "refreshBadges",
    ):
        assert token in html, f"角标提示缺少要素 {token}"
