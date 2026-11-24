"""健康管理：体征记录、用药计划与服药记录（阶段 2）。

体征与服药记录为追加型历史数据：只追加、不被旧记录覆盖；
重复提交凭幂等键去重。
"""
from __future__ import annotations

from app import db, errors, models


# ---------- 体征 ----------

def _validate_vital(vtype: str, value: str) -> str:
    if vtype not in models.VITALS_TYPES:
        raise errors.ValidationError("体征类型无效")
    if value is None or str(value).strip() == "":
        raise errors.ValidationError("体征数值不能为空")
    value = str(value).strip()

    if vtype == models.VIT_BP:
        if "/" not in value:
            raise errors.ValidationError("血压格式应为 收缩压/舒张压，如 120/80")
        sys, dia = value.split("/")
        try:
            sys_v, dia_v = int(sys), int(dia)
        except ValueError:
            raise errors.ValidationError("血压数值必须为整数")
        if not (60 <= sys_v <= 260) or not (30 <= dia_v <= 180):
            raise errors.ValidationError("血压数值超出合理范围")
    elif vtype == models.VIT_GLUCOSE:
        g = float(value)
        if not (1 <= g <= 40):
            raise errors.ValidationError("血糖数值超出合理范围")
    elif vtype == models.VIT_HEART:
        h = int(float(value))
        if not (30 <= h <= 250):
            raise errors.ValidationError("心率数值超出合理范围")
    elif vtype == models.VIT_WEIGHT:
        w = float(value)
        if not (20 <= w <= 300):
            raise errors.ValidationError("体重数值超出合理范围")
    return value


def add_vital(conn, elder_id: int, vtype: str, value: str, unit: str = "",
              measured_at: str | None = None, idempotency_key: str | None = None) -> dict:
    value = _validate_vital(vtype, value)
    now = db.utc_now()
    measured_at = measured_at or now

    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM vitals WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO vitals (elder_id, type, value, unit, measured_at, recorded_by, "
        "idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (elder_id, vtype, value, unit, measured_at, "elder", idempotency_key, now, now),
    )
    vital_id = cur.lastrowid
    db.record_change(conn, "vitals", vital_id, elder_id, "create", f"录入{vtype}", "elder", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM vitals WHERE vital_id=?", (vital_id,)).fetchone())


def list_vitals(conn, elder_id: int, vtype: str | None = None) -> list[dict]:
    if vtype:
        rows = conn.execute(
            "SELECT * FROM vitals WHERE elder_id=? AND type=? ORDER BY measured_at DESC, vital_id DESC",
            (elder_id, vtype),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM vitals WHERE elder_id=? ORDER BY measured_at DESC, vital_id DESC",
            (elder_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def latest_vitals(conn, elder_id: int) -> dict:
    """返回每类体征的最新一条，供家属概览展示。"""
    result = {}
    for vtype in models.VITALS_TYPES:
        row = conn.execute(
            "SELECT * FROM vitals WHERE elder_id=? AND type=? ORDER BY measured_at DESC, vital_id DESC LIMIT 1",
            (elder_id, vtype),
        ).fetchone()
        if row:
            result[vtype] = dict(row)
    return result


# ---------- 用药计划 ----------

def add_medication(conn, elder_id: int, name: str, dosage: str = "",
                   time_rule: str = "", repeat_rule: str = "daily") -> dict:
    if not name or not name.strip():
        raise errors.ValidationError("药品名称不能为空")
    now = db.utc_now()
    cur = conn.execute(
        "INSERT INTO medication_plans (elder_id, name, dosage, time_rule, repeat_rule, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (elder_id, name.strip(), dosage, time_rule, repeat_rule, now, now),
    )
    plan_id = cur.lastrowid
    db.record_change(conn, "medication_plans", plan_id, elder_id, "create", "新增用药计划", "elder", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM medication_plans WHERE plan_id=?", (plan_id,)).fetchone())


def list_medications(conn, elder_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM medication_plans WHERE elder_id=? ORDER BY plan_id", (elder_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def mark_medication(conn, plan_id: int, elder_id: int, status: str,
                    planned_at: str, idempotency_key: str | None = None) -> dict:
    if status not in models.MED_LOG_STATUSES:
        raise errors.ValidationError("服药状态无效")
    plan = conn.execute("SELECT * FROM medication_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if plan is None or plan["elder_id"] != elder_id:
        raise errors.NotFoundError("用药计划不存在")

    now = db.utc_now()
    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM medication_logs WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO medication_logs (plan_id, elder_id, planned_at, status, recorded_at, "
        "idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (plan_id, elder_id, planned_at, status, now, idempotency_key, now, now),
    )
    log_id = cur.lastrowid
    db.record_change(conn, "medication_logs", log_id, elder_id, "create", f"服药{status}", "elder", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM medication_logs WHERE log_id=?", (log_id,)).fetchone())


def latest_medication_status(conn, elder_id: int) -> list[dict]:
    """每个用药计划最近一次服药记录，供两端待办/概览展示。"""
    plans = list_medications(conn, elder_id)
    result = []
    for plan in plans:
        row = conn.execute(
            "SELECT * FROM medication_logs WHERE plan_id=? ORDER BY recorded_at DESC LIMIT 1",
            (plan["plan_id"],),
        ).fetchone()
        item = dict(plan)
        item["latest_log"] = dict(row) if row else None
        result.append(item)
    return result
