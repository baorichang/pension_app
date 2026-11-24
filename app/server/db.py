# -*- coding: utf-8 -*-
"""数据库连接与表结构初始化（阶段0）。

权威数据源为服务端 SQLite；客户端本地仅存缓存/离线副本，不作为长期权威。
所有可变业务表均带 created_at / updated_at / version，用于增量同步与冲突判断。
"""
import os
import sqlite3
import threading

# 默认数据库文件路径；测试通过环境变量 ELDERCARE_DB 指向临时库
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(_BASE_DIR, "data", "eldercare.db")
DB_PATH = os.environ.get("ELDERCARE_DB", DEFAULT_DB)

_lock = threading.Lock()

SCHEMA = """
-- 用户账号
CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    phone        TEXT NOT NULL UNIQUE,
    role         TEXT NOT NULL CHECK (role IN ('elder', 'family')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1
);

-- 亲属绑定关系（老人 <-> 家属，多对多）
CREATE TABLE IF NOT EXISTS family_relations (
    relation_id  TEXT PRIMARY KEY,
    elder_id     TEXT NOT NULL,
    family_id    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('active', 'removed')),
    scope        TEXT NOT NULL DEFAULT 'basic',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (elder_id, family_id),
    FOREIGN KEY (elder_id) REFERENCES users(user_id),
    FOREIGN KEY (family_id) REFERENCES users(user_id)
);

-- 老人健康档案
CREATE TABLE IF NOT EXISTS elder_profile (
    profile_id        TEXT PRIMARY KEY,
    elder_id          TEXT NOT NULL UNIQUE,
    name              TEXT,
    gender            TEXT,
    age               INTEGER,
    blood_type        TEXT,
    chronic_diseases  TEXT,
    medical_history   TEXT,
    allergies         TEXT,
    regular_meds      TEXT,
    emergency_contact TEXT,
    address           TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    version           INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (elder_id) REFERENCES users(user_id)
);

-- 体征记录（追加型历史数据，不可被旧记录覆盖）
CREATE TABLE IF NOT EXISTS vitals (
    vital_id     TEXT PRIMARY KEY,
    elder_id     TEXT NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('bp', 'bg', 'heart_rate', 'weight')),
    value        TEXT NOT NULL,
    unit         TEXT,
    measured_at  TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'elder_app',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (elder_id) REFERENCES users(user_id)
);

-- 用药计划
CREATE TABLE IF NOT EXISTS medication_plans (
    plan_id      TEXT PRIMARY KEY,
    elder_id     TEXT NOT NULL,
    drug_name    TEXT NOT NULL,
    dosage       TEXT,
    schedule_time TEXT,
    repeat_rule  TEXT,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'stopped')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (elder_id) REFERENCES users(user_id)
);

-- 服药记录
CREATE TABLE IF NOT EXISTS medication_logs (
    log_id       TEXT PRIMARY KEY,
    plan_id      TEXT NOT NULL,
    elder_id     TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('taken', 'missed', 'pending')),
    recorded_at  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (plan_id) REFERENCES medication_plans(plan_id),
    FOREIGN KEY (elder_id) REFERENCES users(user_id)
);

-- 服务资源（居家 / 社区 / 机构）
CREATE TABLE IF NOT EXISTS service_resources (
    resource_id    TEXT PRIMARY KEY,
    category       TEXT NOT NULL CHECK (category IN ('home', 'community', 'org')),
    name           TEXT NOT NULL,
    description    TEXT,
    duration_quota TEXT,
    price_range    TEXT,
    location       TEXT,
    event_time     TEXT,
    contact        TEXT,
    media_placeholder TEXT,
    status         TEXT NOT NULL DEFAULT 'on_shelf',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    version        INTEGER NOT NULL DEFAULT 1
);

-- 订单（两端共享同一订单，状态只由服务端状态机流转）
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    elder_id        TEXT NOT NULL,
    placer_id       TEXT NOT NULL,
    placer_role     TEXT NOT NULL CHECK (placer_role IN ('elder', 'family')),
    resource_id     TEXT,
    service_item    TEXT NOT NULL,
    scheduled_time  TEXT,
    address         TEXT,
    amount          TEXT,
    pay_method      TEXT NOT NULL CHECK (pay_method IN ('self', 'family_pay')),
    status          TEXT NOT NULL CHECK (status IN ('pending_pay', 'in_progress', 'completed', 'after_sale')),
    pay_status      TEXT NOT NULL DEFAULT 'unpaid' CHECK (pay_status IN ('unpaid', 'paid', 'refunded')),
    idempotency_key TEXT UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    version         INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (elder_id) REFERENCES users(user_id),
    FOREIGN KEY (placer_id) REFERENCES users(user_id),
    FOREIGN KEY (resource_id) REFERENCES service_resources(resource_id)
);

-- 告警记录
CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    elder_id     TEXT NOT NULL,
    type         TEXT NOT NULL CHECK (type IN ('sos', 'vitals_abnormal', 'missed_med', 'geofence', 'idle')),
    content      TEXT,
    location     TEXT,
    occurred_at  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('unread', 'read', 'contacted')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    version      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (elder_id) REFERENCES users(user_id)
);

-- 消息通知
CREATE TABLE IF NOT EXISTS messages (
    message_id     TEXT PRIMARY KEY,
    receiver_id    TEXT NOT NULL,
    type           TEXT NOT NULL,
    title          TEXT,
    body           TEXT,
    ref_order_id   TEXT,
    read_status    TEXT NOT NULL DEFAULT 'unread' CHECK (read_status IN ('unread', 'read')),
    sent_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    version        INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (receiver_id) REFERENCES users(user_id)
);

-- 隐私授权
CREATE TABLE IF NOT EXISTS consents (
    consent_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    elder_id    TEXT,
    item        TEXT NOT NULL CHECK (item IN ('location', 'mic', 'notification', 'health')),
    status      TEXT NOT NULL CHECK (status IN ('granted', 'revoked')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    version     INTEGER NOT NULL DEFAULT 1,
    UNIQUE (user_id, elder_id, item),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 客户端偏好设置（本地为主，可选同步）
CREATE TABLE IF NOT EXISTS app_settings (
    user_id        TEXT PRIMARY KEY,
    font_level     TEXT NOT NULL DEFAULT 'large',
    voice_broadcast INTEGER NOT NULL DEFAULT 1,
    high_contrast  INTEGER NOT NULL DEFAULT 0,
    voice_input    INTEGER NOT NULL DEFAULT 1,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    version        INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- 同步事件流：记录实体变更，供增量拉取与（模拟）实时推送
CREATE TABLE IF NOT EXISTS sync_events (
    event_id     TEXT PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    elder_id     TEXT,
    change_type  TEXT NOT NULL,
    version      INTEGER NOT NULL,
    summary      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

REQUIRED_TABLES = [
    "users", "family_relations", "elder_profile", "vitals", "medication_plans",
    "medication_logs", "service_resources", "orders", "alerts", "messages",
    "consents", "app_settings", "sync_events",
]

# 需要带版本与时间戳的可变业务表
VERSIONED_TABLES = [
    "users", "family_relations", "elder_profile", "vitals", "medication_plans",
    "medication_logs", "service_resources", "orders", "alerts", "messages",
    "consents", "app_settings",
]


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_connection():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with _lock:
        _ensure_dir()
        conn = get_connection()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()


def reset_db():
    """测试辅助：删除库文件并重建。"""
    with _lock:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        init_db()


if __name__ == "__main__":
    init_db()
    print("数据库已初始化：", DB_PATH)
