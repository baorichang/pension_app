"""SQLite 权威数据库：连接、建表、时间戳与变更日志。

所有业务表均含 created_at / updated_at / version，用于增量同步与冲突判断；
change_log 记录实体变更，供两端增量拉取（sync/pull）使用。
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Optional

SCHEMA_VERSION = "1.0.0"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone            TEXT NOT NULL UNIQUE,
            role             TEXT NOT NULL CHECK (role IN ('elder','family')),
            session_token    TEXT,
            session_expires  TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS family_relations (
            relation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL,
            family_id        INTEGER NOT NULL,
            status           TEXT NOT NULL CHECK (status IN ('active','unbound')),
            scope            TEXT NOT NULL DEFAULT 'health,location,orders,alerts',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1,
            UNIQUE (elder_id, family_id)
        );

        CREATE TABLE IF NOT EXISTS elder_profile (
            profile_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL UNIQUE,
            name             TEXT,
            gender           TEXT,
            age              INTEGER,
            blood_type       TEXT,
            chronic_disease  TEXT,
            history          TEXT,
            allergy          TEXT,
            common_meds      TEXT,
            emergency_contact TEXT,
            address          TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS vitals (
            vital_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL,
            type             TEXT NOT NULL CHECK (type IN ('bp','glucose','heart_rate','weight')),
            value            TEXT NOT NULL,
            unit             TEXT,
            measured_at      TEXT NOT NULL,
            recorded_by      TEXT,
            idempotency_key  TEXT UNIQUE,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS medication_plans (
            plan_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL,
            name             TEXT NOT NULL,
            dosage           TEXT,
            time_rule        TEXT,
            repeat_rule      TEXT,
            status           TEXT NOT NULL DEFAULT 'active',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS medication_logs (
            log_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id          INTEGER NOT NULL,
            elder_id         INTEGER NOT NULL,
            planned_at       TEXT NOT NULL,
            status           TEXT NOT NULL CHECK (status IN ('taken','missed')),
            recorded_at      TEXT NOT NULL,
            idempotency_key  TEXT UNIQUE,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS service_resources (
            resource_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            category         TEXT NOT NULL CHECK (category IN ('home','community','org')),
            name             TEXT NOT NULL,
            description      TEXT,
            duration_or_quota TEXT,
            price_range      TEXT,
            location         TEXT,
            event_time       TEXT,
            contact          TEXT,
            image_placeholder TEXT,
            status           TEXT NOT NULL DEFAULT 'on',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL,
            orderer_id       INTEGER NOT NULL,
            orderer_role     TEXT NOT NULL CHECK (orderer_role IN ('elder','family')),
            resource_id      INTEGER,
            service_item     TEXT NOT NULL,
            appointment_time TEXT,
            address          TEXT,
            amount           REAL,
            pay_method       TEXT NOT NULL CHECK (pay_method IN ('self','family_pay')),
            status           TEXT NOT NULL DEFAULT 'pending_pay',
            pay_status       TEXT NOT NULL DEFAULT 'unpaid',
            idempotency_key  TEXT UNIQUE,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS alerts (
            alert_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         INTEGER NOT NULL,
            type             TEXT NOT NULL CHECK (type IN ('SOS','vitals_abnormal','missed_med','geofence','idle')),
            content          TEXT,
            location         TEXT,
            occurred_at      TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'unread'
                             CHECK (status IN ('unread','read','contacted')),
            idempotency_key  TEXT UNIQUE,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS messages (
            message_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            receiver_id      INTEGER NOT NULL,
            sender_id        INTEGER,
            type             TEXT NOT NULL CHECK (type IN ('notice','reminder','letter','announcement')),
            title            TEXT,
            body             TEXT,
            ref_type         TEXT,
            ref_id           INTEGER,
            read_status      TEXT NOT NULL DEFAULT 'unread',
            idempotency_key  TEXT UNIQUE,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS consents (
            consent_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            elder_id         INTEGER,
            item             TEXT NOT NULL CHECK (item IN ('location','mic','notification','health')),
            granted          INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1,
            UNIQUE (user_id, elder_id, item)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            user_id          INTEGER PRIMARY KEY,
            font_level       TEXT NOT NULL DEFAULT 'large',
            voice_broadcast  INTEGER NOT NULL DEFAULT 1,
            high_contrast    INTEGER NOT NULL DEFAULT 0,
            voice_input      INTEGER NOT NULL DEFAULT 1,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sos_settings (
            elder_id         INTEGER PRIMARY KEY,
            fall_detection   INTEGER NOT NULL DEFAULT 1,
            geofence         INTEGER NOT NULL DEFAULT 1,
            idle_reminder    INTEGER NOT NULL DEFAULT 0,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS change_log (
            log_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type      TEXT NOT NULL,
            entity_id        INTEGER NOT NULL,
            elder_id         INTEGER,
            op               TEXT NOT NULL,
            summary          TEXT,
            side             TEXT,
            changed_at       TEXT NOT NULL
        );
        """
    )
    conn.commit()


def record_change(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    elder_id: Optional[int],
    op: str,
    summary: str = "",
    side: str = "",
    now: Optional[str] = None,
) -> None:
    """记录一次实体变更，供增量同步拉取。"""
    conn.execute(
        "INSERT INTO change_log (entity_type, entity_id, elder_id, op, summary, side, changed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, elder_id, op, summary, side, now or utc_now()),
    )
