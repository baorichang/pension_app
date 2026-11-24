# -*- coding: utf-8 -*-
"""阶段0 测试：工程骨架、表结构、版本字段、约束完整性。"""
import os
import sys
import tempfile
import unittest

# 先指向临时库，再导入 db 模块
_tmp = tempfile.mkdtemp()
os.environ["ELDERCARE_DB"] = os.path.join(_tmp, "stage0_test.db")

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _APP_DIR)

from server import db  # noqa: E402


class TestStage0Schema(unittest.TestCase):
    def setUp(self):
        db.reset_db()

    def test_all_required_tables_exist(self):
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r["name"] for r in rows}
        for table in db.REQUIRED_TABLES:
            self.assertIn(table, names, f"缺少数据表：{table}")
        conn.close()

    def test_versioned_tables_have_timestamp_and_version(self):
        conn = db.get_connection()
        for table in db.VERSIONED_TABLES:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            self.assertIn("created_at", cols, f"{table} 缺少 created_at")
            self.assertIn("updated_at", cols, f"{table} 缺少 updated_at")
            self.assertIn("version", cols, f"{table} 缺少 version")
        conn.close()

    def test_foreign_keys_enabled(self):
        conn = db.get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1, "外键约束未开启")
        conn.close()

    def test_role_enum_constraint_rejects_bad_role(self):
        conn = db.get_connection()
        with self.assertRaises(sqlite3_integrity_error()):
            conn.execute(
                "INSERT INTO users(user_id, phone, role) VALUES (?, ?, ?)",
                ("u-bad", "13900000000", "doctor"),
            )
            conn.commit()
        conn.close()

    def test_init_db_is_idempotent(self):
        db.init_db()
        db.init_db()
        conn = db.get_connection()
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertEqual(count, 0)
        conn.close()


def sqlite3_integrity_error():
    import sqlite3
    return sqlite3.IntegrityError


if __name__ == "__main__":
    unittest.main(verbosity=2)
