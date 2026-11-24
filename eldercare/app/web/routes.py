"""HTTP 路由：把领域服务包装为 REST 接口，首版用 X-User-Id 头标识当前用户。"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app import (alerts, auth, bindings, errors, family, health, messages, models,
                 orders, profile, resources, settings, sos, sync)
from app.web.deps import get_conn
from app.web.push import hub

router = APIRouter()
Conn = sqlite3.Connection


# ---------- 请求模型 ----------

class LoginBody(BaseModel):
    phone: str
    role: str
    code: str = auth.DEV_FIXED_CODE


class ProfileBody(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    blood_type: Optional[str] = None
    chronic_disease: Optional[str] = None
    history: Optional[str] = None
    allergy: Optional[str] = None
    common_meds: Optional[str] = None
    emergency_contact: Optional[str] = None
    address: Optional[str] = None


class VitalBody(BaseModel):
    type: str
    value: str
    unit: str = ""
    source: str = "manual"
    device_type: Optional[str] = None
    idempotency_key: Optional[str] = None


class MedicationBody(BaseModel):
    name: str
    dosage: str = ""
    time_rule: str = ""


class TakenBody(BaseModel):
    status: str
    planned_at: Optional[str] = None
    idempotency_key: Optional[str] = None


class SosBody(BaseModel):
    location: str = ""
    note: str = ""


class SosSettingsBody(BaseModel):
    fall_detection: Optional[int] = None
    geofence: Optional[int] = None
    idle_reminder: Optional[int] = None


class OrderBody(BaseModel):
    elder_id: Optional[int] = None
    service_item: str
    resource_id: Optional[int] = None
    appointment_time: str = ""
    address: str = ""
    amount: float = 0.0


class AlertStatusBody(BaseModel):
    status: str


class SettingsBody(BaseModel):
    font_level: Optional[str] = None
    voice_broadcast: Optional[int] = None
    high_contrast: Optional[int] = None
    voice_input: Optional[int] = None


def _uid(request: Request) -> int:
    raw = request.headers.get("X-User-Id")
    if not raw:
        raise errors.PermissionError("未登录，请先在演示页登录")
    try:
        return int(raw)
    except ValueError as exc:
        raise errors.ValidationError("用户标识无效") from exc


# ---------- 认证 ----------

@router.post("/api/auth/login")
def login(body: LoginBody, conn: Conn = Depends(get_conn)):
    user = auth.login(conn, body.phone, body.code, body.role)
    return errors.ok({**user, "token": str(user["user_id"])})


@router.get("/api/me")
def me(request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    row = conn.execute("SELECT user_id, phone, role FROM users WHERE user_id=?", (uid,)).fetchone()
    if row is None:
        raise errors.NotFoundError("用户不存在")
    data = dict(row)
    data["settings"] = settings.get_settings(conn, uid)
    return errors.ok(data)


# ---------- 老人端：档案 / 健康 / 用药 / SOS / 消息 / 设置 ----------

@router.get("/api/profile")
def get_profile(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(profile.get_profile(conn, _uid(request)))


@router.put("/api/profile")
def put_profile(body: ProfileBody, request: Request, conn: Conn = Depends(get_conn)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return errors.ok(profile.upsert_profile(conn, _uid(request), data))


@router.get("/api/vitals")
def list_vitals(type: Optional[str] = None, request: Request = None, conn: Conn = Depends(get_conn)):
    return errors.ok(health.list_vitals(conn, _uid(request), type))


@router.post("/api/vitals")
async def add_vital(body: VitalBody, request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    vital = health.add_vital(conn, uid, body.type, body.value, body.unit,
                             idempotency_key=body.idempotency_key,
                             source=body.source, device_type=body.device_type)
    alert = alerts.evaluate_vitals(conn, uid, vital)
    if alert:
        await hub.broadcast_to_families(conn, uid, {"type": "alert_new", "data": alert})
    return errors.ok(vital)


@router.get("/api/medications")
def list_medications(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(health.latest_medication_status(conn, _uid(request)))


@router.post("/api/medications")
def add_medication(body: MedicationBody, request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(health.add_medication(conn, _uid(request), body.name, body.dosage, body.time_rule))


@router.post("/api/medications/{plan_id}/taken")
def mark_taken(plan_id: int, body: TakenBody, request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(health.mark_medication(conn, plan_id, _uid(request), body.status,
                                            body.planned_at, idempotency_key=body.idempotency_key))


@router.post("/api/sos")
async def create_sos(body: SosBody, request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    alert = sos.create_sos(conn, uid, body.location, body.note)
    await hub.broadcast_to_families(conn, uid, {"type": "alert_new", "data": alert})
    return errors.ok(alert)


@router.get("/api/sos/settings")
def get_sos_settings(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(sos.get_sos_settings(conn, _uid(request)))


@router.put("/api/sos/settings")
def put_sos_settings(body: SosSettingsBody, request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(sos.set_sos_settings(conn, _uid(request), body.fall_detection,
                                          body.geofence, body.idle_reminder))


@router.get("/api/messages")
def list_messages(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(messages.list_messages(conn, _uid(request)))


@router.post("/api/messages/{message_id}/read")
def read_message(message_id: int, conn: Conn = Depends(get_conn)):
    return errors.ok(messages.mark_read(conn, message_id))


@router.get("/api/settings")
def get_settings(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(settings.get_settings(conn, _uid(request)))


@router.put("/api/settings")
def put_settings(body: SettingsBody, request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(settings.update_settings(
        conn, _uid(request), body.font_level, body.voice_broadcast,
        body.high_contrast, body.voice_input))


@router.get("/api/orders")
def my_orders(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(orders.list_orders_by_elder(conn, _uid(request)))


@router.post("/api/orders")
async def self_create_order(body: OrderBody, request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    order = orders.create_order(
        conn, uid, uid, models.ROLE_ELDER,
        service_item=body.service_item, resource_id=body.resource_id,
        appointment_time=body.appointment_time, address=body.address,
        amount=body.amount, pay_method=models.PAY_SELF,
    )
    await hub.send(uid, {"type": "order_update", "data": order})
    return errors.ok(order)


# ---------- 子女端：概览 / 详情 / 告警 / 订单 ----------

@router.get("/api/family/overviews")
def family_overviews(request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    elders = bindings.list_elders_of_family(conn, uid)
    return errors.ok([family.get_overview(conn, uid, e) for e in elders])


@router.get("/api/family/elders/{elder_id}/detail")
def family_detail(elder_id: int, request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(family.get_detail(conn, _uid(request), elder_id))


@router.get("/api/family/alerts")
def family_alerts(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(alerts.list_alerts(conn, _uid(request)))


@router.post("/api/family/alerts/{alert_id}/read")
def family_read_alert(alert_id: int, body: AlertStatusBody, request: Request,
                      conn: Conn = Depends(get_conn)):
    return errors.ok(alerts.mark_status(conn, _uid(request), alert_id, body.status))


@router.get("/api/family/orders")
def family_orders(request: Request, conn: Conn = Depends(get_conn)):
    return errors.ok(orders.list_orders_by_family(conn, _uid(request)))


@router.post("/api/family/orders")
async def family_create_order(body: OrderBody, request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    order = orders.create_order(
        conn, body.elder_id, uid, models.ROLE_FAMILY,
        service_item=body.service_item, resource_id=body.resource_id,
        appointment_time=body.appointment_time, address=body.address,
        amount=body.amount, pay_method=models.PAY_FAMILY,
    )
    await hub.broadcast_to_elder(body.elder_id, {"type": "order_update", "data": order})
    await hub.send(uid, {"type": "order_update", "data": order})
    return errors.ok(order)


@router.post("/api/family/orders/{order_id}/pay")
async def family_pay_order(order_id: int, request: Request, conn: Conn = Depends(get_conn)):
    uid = _uid(request)
    order = orders.pay_order(conn, uid, order_id)
    await hub.broadcast_to_elder(order["elder_id"], {"type": "order_update", "data": order})
    await hub.send(uid, {"type": "order_update", "data": order})
    return errors.ok(order)


# ---------- 公共：资源 / 同步 / 健康检查 ----------

@router.get("/api/resources")
def list_resources(category: Optional[str] = None, conn: Conn = Depends(get_conn)):
    return errors.ok(resources.list_resources(conn, category))


@router.get("/api/sync/changes")
def sync_changes(since: str = "", conn: Conn = Depends(get_conn)):
    return errors.ok(sync.pull_changes(conn, since))


@router.get("/api/health")
def health_check():
    return errors.ok({"status": "up"})
