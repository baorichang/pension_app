"""阶段 2 测试：档案、体征、用药、SOS 与离线队列底座。"""
import pytest

from app import auth, errors, health, models, offline, profile, sos


def _elder(conn, phone="13700000001"):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def test_profile_upsert_create_then_update(conn):
    elder = _elder(conn)
    p = profile.upsert_profile(conn, elder["user_id"], {
        "name": "王阿姨", "age": 68, "allergy": "青霉素", "address": "幸福小区 1 栋"
    })
    assert p["name"] == "王阿姨"
    v1 = p["version"]

    p2 = profile.upsert_profile(conn, elder["user_id"], {"age": 69, "chronic_disease": "高血压"})
    assert p2["age"] == 69
    assert p2["chronic_disease"] == "高血压"
    assert p2["version"] == v1 + 1


def test_vital_recorded_and_history_queryable(conn):
    elder = _elder(conn)
    health.add_vital(conn, elder["user_id"], models.VIT_BP, "120/80", "mmHg")
    health.add_vital(conn, elder["user_id"], models.VIT_HEART, "72", "次/分")

    history = health.list_vitals(conn, elder["user_id"])
    assert len(history) == 2
    latest = health.latest_vitals(conn, elder["user_id"])
    assert latest[models.VIT_BP]["value"] == "120/80"
    assert latest[models.VIT_HEART]["value"] == "72"


def test_vital_rejects_empty_and_out_of_range(conn):
    elder = _elder(conn)
    with pytest.raises(errors.ValidationError):
        health.add_vital(conn, elder["user_id"], models.VIT_BP, "")
    with pytest.raises(errors.ValidationError):
        health.add_vital(conn, elder["user_id"], models.VIT_HEART, "999")
    with pytest.raises(errors.ValidationError):
        health.add_vital(conn, elder["user_id"], models.VIT_GLUCOSE, "99")


def test_vital_idempotent_key_prevents_duplicate(conn):
    elder = _elder(conn)
    first = health.add_vital(conn, elder["user_id"], models.VIT_WEIGHT, "60", "kg", idempotency_key="k1")
    second = health.add_vital(conn, elder["user_id"], models.VIT_WEIGHT, "61", "kg", idempotency_key="k1")
    assert first["vital_id"] == second["vital_id"]
    assert len(health.list_vitals(conn, elder["user_id"])) == 1


def test_medication_add_and_mark_taken(conn):
    elder = _elder(conn)
    med = health.add_medication(conn, elder["user_id"], "降压药", "1 片", "08:00")
    health.mark_medication(conn, med["plan_id"], elder["user_id"], models.MED_TAKEN, "2026-11-24 08:00")

    meds = health.latest_medication_status(conn, elder["user_id"])
    assert meds[0]["name"] == "降压药"
    assert meds[0]["latest_log"]["status"] == models.MED_TAKEN


def test_medication_name_required(conn):
    elder = _elder(conn)
    with pytest.raises(errors.ValidationError):
        health.add_medication(conn, elder["user_id"], "  ")


def test_sos_record_created_with_location_and_note(conn):
    elder = _elder(conn)
    alert = sos.create_sos(conn, elder["user_id"], location="幸福小区 1 栋", note="头晕不适")
    records = sos.list_sos_records(conn, elder["user_id"])
    assert len(records) == 1
    assert records[0]["location"] == "幸福小区 1 栋"
    assert records[0]["content"] == "头晕不适"
    assert records[0]["type"] == models.ALERT_SOS
    assert alert["status"] == models.ALERT_UNREAD


def test_sos_idempotent_duplicate_submit(conn):
    elder = _elder(conn)
    a = sos.create_sos(conn, elder["user_id"], "家中", idempotency_key="sos-1")
    b = sos.create_sos(conn, elder["user_id"], "家中", idempotency_key="sos-1")
    assert a["alert_id"] == b["alert_id"]
    assert len(sos.list_sos_records(conn, elder["user_id"])) == 1


def test_sos_settings_persist(conn):
    elder = _elder(conn)
    settings = sos.set_sos_settings(conn, elder["user_id"], idle_reminder=1, geofence=0)
    assert settings["idle_reminder"] == 1
    assert settings["geofence"] == 0
    again = sos.get_sos_settings(conn, elder["user_id"])
    assert again["idle_reminder"] == 1


def test_offline_queue_add_pending_done(conn):
    q = offline.OfflineQueue()
    k = q.add("vitals", "create", {"type": "bp", "value": "130/85"}, idempotency_key="v-1")
    assert len(q) == 1
    assert q.pending()[0]["idempotency_key"] == "v-1"
    q.mark_done(k)
    assert len(q) == 0
