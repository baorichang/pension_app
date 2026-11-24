"""阶段 0 测试：工程骨架与数据库建表。

验收点：核心表全部建立；业务记录含时间戳与版本；变更日志可写可读；
约束（角色、外键）生效。
"""
import sqlite3

import pytest

from app import db

EXPECTED_TABLES = {
    "users", "family_relations", "elder_profile", "vitals",
    "medication_plans", "medication_logs", "service_resources", "orders",
    "alerts", "messages", "consents", "app_settings", "change_log",
}


def test_all_core_tables_exist(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    tables = {r["name"] for r in rows}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"缺少核心表: {missing}"


def test_user_record_has_timestamp_and_version(conn):
    now = db.utc_now()
    conn.execute(
        "INSERT INTO users (phone, role, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("13800000001", "elder", now, now),
    )
    row = conn.execute("SELECT * FROM users WHERE phone=?", ("13800000001",)).fetchone()
    assert row["user_id"] > 0
    assert row["created_at"] == now
    assert row["updated_at"] == now
    assert row["version"] == 1


def test_change_log_writable_and_queryable(conn):
    now = db.utc_now()
    db.record_change(conn, "profile", 1, 1, "update", "档案更新", "elder", now)
    row = conn.execute("SELECT * FROM change_log WHERE entity_type='profile'").fetchone()
    assert row["entity_id"] == 1
    assert row["op"] == "update"
    assert row["changed_at"] == now


def test_role_check_constraint_rejects_invalid(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (phone, role, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("13800000002", "ghost", db.utc_now(), db.utc_now()),
        )


def test_foreign_keys_enabled(conn):
    pragma = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert pragma == 1
