"""阶段 10（问题 4）：登录界面要素与登录链路。"""
from __future__ import annotations

import pathlib

import pytest

from app import auth, errors, models

HTML = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "index.html"


def test_login_page_elements_present():
    html = HTML.read_text(encoding="utf-8")
    for token in (
        'id="lPhone"', 'id="lCode"', 'id="lAgree"',
        'data-action="login"', 'data-action="pick-login-end"', 'data-action="logout"',
    ):
        assert token in html, f"登录界面缺少要素 {token}"


def test_login_success_issues_token(conn):
    user = auth.login(conn, "13800000001", auth.DEV_FIXED_CODE, models.ROLE_ELDER)
    assert user["user_id"] > 0
    assert user["role"] == models.ROLE_ELDER
    assert user["token"]
    assert auth.get_user_by_token(conn, user["token"]) is not None


def test_wrong_code_rejected(conn):
    with pytest.raises(errors.ValidationError):
        auth.login(conn, "13800000002", "000000", models.ROLE_ELDER)
