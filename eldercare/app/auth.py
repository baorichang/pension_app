"""认证：验证码登录、会话 token 与角色识别（阶段 1）。

首版短信为开发期固定验证码占位；生产环境替换为真实短信服务。
"""
from __future__ import annotations

import datetime as _dt
import uuid

from app import db, errors, models

DEV_FIXED_CODE = "123456"
SESSION_TTL = _dt.timedelta(days=7)


def send_sms_code(phone: str) -> dict:
    """发送登录/绑定验证码（占位：返回固定验证码供开发与测试）。"""
    if not phone or len(phone) < 5:
        raise errors.ValidationError("手机号格式不正确")
    return {"phone": phone, "code": DEV_FIXED_CODE}


def _issue_token() -> str:
    return uuid.uuid4().hex


def login(conn, phone: str, code: str, role: str) -> dict:
    if role not in models.ROLES:
        raise errors.ValidationError("角色无效")
    if code != DEV_FIXED_CODE:
        raise errors.ValidationError("验证码错误")

    now = db.utc_now()
    row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()

    if row is None:
        cur = conn.execute(
            "INSERT INTO users (phone, role, session_token, session_expires, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (phone, role, None, None, now, now),
        )
        user_id = cur.lastrowid
    else:
        if row["role"] != role:
            raise errors.ValidationError("该手机号已注册为其他角色")
        user_id = row["user_id"]

    token = _issue_token()
    expires = (_dt.datetime.now(_dt.timezone.utc) + SESSION_TTL).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE users SET session_token=?, session_expires=?, updated_at=?, version=version+1 WHERE user_id=?",
        (token, expires, now, user_id),
    )
    db.record_change(conn, "users", user_id, None, "login", f"{role} 登录", role, now)
    conn.commit()

    return {"user_id": user_id, "phone": phone, "role": role, "token": token}


def get_user_by_token(conn, token: str):
    if not token:
        return None
    row = conn.execute("SELECT * FROM users WHERE session_token=?", (token,)).fetchone()
    if row is None:
        return None
    if row["session_expires"] and row["session_expires"] < db.utc_now():
        return None
    return row
