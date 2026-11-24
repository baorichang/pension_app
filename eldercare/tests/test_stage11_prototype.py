"""阶段 11（问题 5）：按线框原型对齐导航、分类资源与页面入口。"""
from __future__ import annotations

import pathlib

import pytest

from app import errors, models, resources

HTML = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "index.html"


def test_resources_filter_by_category(conn):
    resources.add_resource(conn, models.RES_HOME, "助浴服务", "上门洗浴")
    resources.add_resource(conn, models.RES_COMMUNITY, "社区书法课", "活动")
    resources.add_resource(conn, models.RES_ORG, "康乐养老院", "机构")

    home = resources.list_resources(conn, models.RES_HOME)
    assert all(r["category"] == models.RES_HOME for r in home)
    assert len(home) == 1

    org = resources.list_resources(conn, models.RES_ORG)
    assert len(org) == 1 and org[0]["name"] == "康乐养老院"

    all_res = resources.list_resources(conn)
    assert len(all_res) == 3


def test_invalid_category_rejected(conn):
    with pytest.raises(errors.ValidationError):
        resources.list_resources(conn, "airport")


def test_prototype_nav_and_entries_present():
    html = HTML.read_text(encoding="utf-8")
    for token in (
        'data-tab="sos"',            # 老人端中央 SOS 入口
        'data-action="pick-cat"',    # 服务分类切换
        'data-action="browse-resources"',  # 子女端找服务
        "renderElderSos",            # 独立 SOS 视图
        "我的订单",                  # 老人端订单入口
        "居家上门", "社区服务", "养老机构",
    ):
        assert token in html, f"原型对齐缺少要素 {token}"
