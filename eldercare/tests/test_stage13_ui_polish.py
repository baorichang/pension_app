"""阶段 13：界面细化——服务项目下拉、提示文案、状态中文、状态栏、AI 助手悬浮球。"""
from __future__ import annotations

import pathlib

HTML = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "index.html"


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def test_service_item_dropdowns_present():
    html = _html()
    # 老人端本人下单、子女端代付下单的服务项目均为下拉框
    assert '<select id="oItem"' in html
    assert '<select id="fItem"' in html
    assert "SERVICE_ITEMS" in html


def test_vital_hint_text_removed():
    html = _html()
    assert "点击下方类型即可录入" not in html


def test_alert_status_localized():
    html = _html()
    for token in ("ALERT_STATUS", "未读", "已读", "已联系", "ALERT_STATUS[a.status]"):
        assert token in html, f"告警状态中文映射缺少 {token}"


def test_status_bar_clock_and_icons():
    html = _html()
    for token in ('id="statusClock"', "updateClock", "status-icons", "batt-shell", "batt-level",
                   '<span class="wifi">', ".wifi i"):
        assert token in html, f"状态栏缺少要素 {token}"
    # WiFi 不再使用 emoji 占位
    assert "📶" not in html


def test_ai_assistant_floating_ball():
    html = _html()
    for token in (
        'class="ai-ball"', 'id="aiBall"', 'id="aiPanel"', 'id="aiMsgs"', 'id="aiInput"',
        'data-action="open-ai"', 'data-action="close-ai"', 'data-action="send-ai"',
        "aiReply", "renderAiBall", "ec_ai_ball", 'id="setAiBall"',
        "initBallDrag", "ec_ai_pos", "ballDrag", "state.aiPos",
    ):
        assert token in html, f"AI 助手缺少要素 {token}"
