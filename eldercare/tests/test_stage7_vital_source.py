"""阶段 7（问题 1）：体征支持手动输入与智能设备录入。"""
import pytest

from app import auth, errors, health, models


def _elder(conn, phone="13711110001"):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def test_manual_entry_defaults_to_manual_source(conn):
    elder = _elder(conn)
    vital = health.add_vital(conn, elder["user_id"], models.VIT_HEART, "72", "次/分")
    assert vital["source"] == models.VIT_SOURCE_MANUAL
    assert vital["device_type"] is None


def test_device_entry_records_device_type(conn):
    elder = _elder(conn)
    vital = health.add_vital(
        conn, elder["user_id"], models.VIT_HEART, "76", "次/分",
        source=models.VIT_SOURCE_DEVICE, device_type=models.DEVICE_BAND,
    )
    assert vital["source"] == models.VIT_SOURCE_DEVICE
    assert vital["device_type"] == models.DEVICE_BAND

    bp = health.add_vital(
        conn, elder["user_id"], models.VIT_BP, "122/78", "mmHg",
        source=models.VIT_SOURCE_DEVICE, device_type=models.DEVICE_BP_MONITOR,
    )
    assert bp["source"] == models.VIT_SOURCE_DEVICE
    assert bp["device_type"] == models.DEVICE_BP_MONITOR


def test_device_entry_without_device_type_is_allowed(conn):
    elder = _elder(conn)
    vital = health.add_vital(
        conn, elder["user_id"], models.VIT_WEIGHT, "60", "kg",
        source=models.VIT_SOURCE_DEVICE,
    )
    assert vital["source"] == models.VIT_SOURCE_DEVICE
    assert vital["device_type"] is None


def test_invalid_source_rejected(conn):
    elder = _elder(conn)
    with pytest.raises(errors.ValidationError):
        health.add_vital(conn, elder["user_id"], models.VIT_HEART, "72", source="voice")


def test_invalid_device_type_rejected(conn):
    elder = _elder(conn)
    with pytest.raises(errors.ValidationError):
        health.add_vital(
            conn, elder["user_id"], models.VIT_BP, "122/78",
            source=models.VIT_SOURCE_DEVICE, device_type="drone",
        )


def test_manual_entry_clears_device_type(conn):
    elder = _elder(conn)
    vital = health.add_vital(
        conn, elder["user_id"], models.VIT_HEART, "70",
        source=models.VIT_SOURCE_MANUAL, device_type=models.DEVICE_BAND,
    )
    assert vital["source"] == models.VIT_SOURCE_MANUAL
    assert vital["device_type"] is None
