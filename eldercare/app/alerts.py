"""告警中心：告警生成、规则判断、家属视角列表与已读状态（阶段 3）。

告警在服务端生成唯一记录；家属只能查看已绑定老人的告警；
已读/已联系状态回写服务端，两端一致。
"""
from __future__ import annotations

from app import bindings, db, errors, models


def _insert_alert(conn, elder_id: int, atype: str, content: str, location: str = "",
                  idempotency_key: str | None = None) -> dict:
    if atype not in models.ALERT_TYPES:
        raise errors.ValidationError("告警类型无效")
    now = db.utc_now()

    if idempotency_key:
        dup = conn.execute(
            "SELECT * FROM alerts WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if dup:
            return dict(dup)

    cur = conn.execute(
        "INSERT INTO alerts (elder_id, type, content, location, occurred_at, status, "
        "idempotency_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (elder_id, atype, content, location, now, models.ALERT_UNREAD,
         idempotency_key, now, now),
    )
    alert_id = cur.lastrowid
    db.record_change(conn, "alerts", alert_id, elder_id, "create", f"告警 {atype}", "system", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchone())


def raise_alert(conn, elder_id: int, atype: str, content: str, location: str = "",
                idempotency_key: str | None = None) -> dict:
    return _insert_alert(conn, elder_id, atype, content, location, idempotency_key)


# ---------- 规则判断 ----------

def evaluate_vitals(conn, elder_id: int, vital: dict) -> dict | None:
    """根据体征阈值判断是否生成体征异常告警；返回告警或 None。"""
    vtype = vital["type"]
    abnormal = False
    detail = ""

    if vtype == models.VIT_BP:
        sys_s, dia_s = vital["value"].split("/")
        sys_v, dia_v = int(sys_s), int(dia_s)
        if sys_v >= 180 or sys_v <= 90 or dia_v >= 110:
            abnormal, detail = True, f"血压异常 {vital['value']} mmHg"
    elif vtype == models.VIT_GLUCOSE:
        g = float(vital["value"])
        if g >= 11.1 or g <= 3.9:
            abnormal, detail = True, f"血糖异常 {vital['value']} mmol/L"
    elif vtype == models.VIT_HEART:
        h = int(float(vital["value"]))
        if h >= 120 or h <= 50:
            abnormal, detail = True, f"心率异常 {vital['value']} 次/分"

    if not abnormal:
        return None
    return _insert_alert(
        conn, elder_id, models.ALERT_VITALS_ABNORMAL, detail,
        idempotency_key=f"vitals_abnormal:{elder_id}:{vital['vital_id']}",
    )


def raise_missed_med(conn, elder_id: int, plan_id: int, drug_name: str, planned_at: str) -> dict:
    return _insert_alert(
        conn, elder_id, models.ALERT_MISSED_MED,
        f"未按时服药：{drug_name}（计划 {planned_at}）",
        idempotency_key=f"missed_med:{plan_id}:{planned_at}",
    )


def raise_geofence(conn, elder_id: int, location: str) -> dict:
    return _insert_alert(conn, elder_id, models.ALERT_GEOFENCE, "离开安全围栏区域", location)


def raise_idle(conn, elder_id: int, minutes: int) -> dict:
    return _insert_alert(conn, elder_id, models.ALERT_IDLE, f"长时间无活动（{minutes} 分钟）")


# ---------- 家属视角 ----------

def list_alerts_unscoped(conn, elder_id: int) -> list[dict]:
    """按老人直查告警（内部聚合用，鉴权由调用方完成）。"""
    rows = conn.execute(
        "SELECT * FROM alerts WHERE elder_id=? ORDER BY occurred_at DESC", (elder_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_alerts(conn, family_id: int, elder_id: int | None = None) -> list[dict]:
    allowed = set(bindings.list_elders_of_family(conn, family_id))
    if not allowed:
        return []
    if elder_id is not None:
        if elder_id not in allowed:
            raise errors.PermissionError("无权查看该老人告警")
        rows = conn.execute(
            "SELECT * FROM alerts WHERE elder_id=? ORDER BY occurred_at DESC", (elder_id,)
        ).fetchall()
    else:
        placeholders = ",".join("?" for _ in allowed)
        rows = conn.execute(
            f"SELECT * FROM alerts WHERE elder_id IN ({placeholders}) ORDER BY occurred_at DESC",
            tuple(allowed),
        ).fetchall()
    return [dict(r) for r in rows]


def count_unread(conn, family_id: int) -> int:
    """未处理（未读）告警条数，供家属端导航角标提示。"""
    allowed = bindings.list_elders_of_family(conn, family_id)
    if not allowed:
        return 0
    placeholders = ",".join("?" for _ in allowed)
    row = conn.execute(
        f"SELECT COUNT(*) AS c FROM alerts WHERE elder_id IN ({placeholders}) AND status='unread'",
        tuple(allowed),
    ).fetchone()
    return row["c"]


def mark_status(conn, family_id: int, alert_id: int, status: str) -> dict:
    if status not in (models.ALERT_READ, models.ALERT_CONTACTED):
        raise errors.ValidationError("告警状态无效")
    alert = conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchone()
    if alert is None:
        raise errors.NotFoundError("告警不存在")
    bindings.assert_can_access(conn, family_id, alert["elder_id"])

    now = db.utc_now()
    conn.execute(
        "UPDATE alerts SET status=?, updated_at=?, version=version+1 WHERE alert_id=?",
        (status, now, alert_id),
    )
    db.record_change(conn, "alerts", alert_id, alert["elder_id"], "update", f"告警状态 {status}", "family", now)
    conn.commit()
    return dict(conn.execute("SELECT * FROM alerts WHERE alert_id=?", (alert_id,)).fetchone())
