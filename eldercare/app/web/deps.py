"""HTTP 层公共依赖：服务端 SQLite 连接、初始化与演示种子数据。"""
from __future__ import annotations

import pathlib
import sqlite3

from fastapi import Depends

from app import auth, bindings, db, health, messages, models, orders, profile, resources

BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "server.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_conn():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def seed(conn: sqlite3.Connection) -> None:
    """首次启动写入演示账号与基础数据；已有数据则跳过。"""
    if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] > 0:
        return

    elder = auth.login(conn, "13300000001", auth.DEV_FIXED_CODE, models.ROLE_ELDER)
    fam = auth.login(conn, "13300000002", auth.DEV_FIXED_CODE, models.ROLE_FAMILY)
    bindings.bind(conn, elder["user_id"], fam["user_id"])

    profile.upsert_profile(
        conn, elder["user_id"],
        {"name": "王阿姨", "gender": "女", "age": 68, "chronic_disease": "高血压",
         "allergy": "青霉素", "address": "幸福小区 1 栋",
         "emergency_contact": "女儿 13300000002"},
    )
    health.add_vital(conn, elder["user_id"], models.VIT_BP, "122/78", "mmHg")
    health.add_vital(conn, elder["user_id"], models.VIT_HEART, "74", "次/分")
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    health.mark_medication(conn, med["plan_id"], elder["user_id"], models.MED_TAKEN, "2026-11-24 08:00")

    resources.add_resource(conn, models.RES_HOME, "助浴服务", "上门洗浴 45 分钟",
                           "45 分钟", "¥80 起", "幸福小区", "", "物业 13300000000")
    resources.add_resource(conn, models.RES_COMMUNITY, "社区书法课", "周三上午书法活动",
                           "名额 20", "免费", "社区活动室", "周三 09:30", "社区 13300000000")
    resources.add_resource(conn, models.RES_ORG, "康乐养老院", "环境与床位介绍占位",
                           "床位充足", "¥3000 起/月", "康乐路 8 号", "", "0551-00000000")

    orders.create_order(conn, elder["user_id"], elder["user_id"], models.ROLE_ELDER,
                        "助洁服务", amount=60.0, pay_method=models.PAY_SELF)
    messages.send_message(conn, elder["user_id"], fam["user_id"], models.MSG_LETTER,
                          "留言", "妈妈注意按时吃药")


def init_server_db() -> None:
    conn = _connect()
    db.init_db(conn)
    seed(conn)
    conn.close()
